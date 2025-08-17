# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class QuoteRequestWizard(models.TransientModel):
    _name = 'quote.request.wizard'
    _description = 'Quote Request Wizard'

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True, readonly=True)
    underwriter_ids = fields.Many2many(
        'res.partner',
        string='Underwriters',
        domain=[('is_insurer', '=', True)],
        required=True
    )
    subject = fields.Char(string='Subject', required=True)
    body = fields.Html(string='Body', required=True)

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        lead_id = self.env.context.get('active_id')
        if lead_id and 'lead_id' in fields:
            lead = self.env['crm.lead'].browse(lead_id)
            result['lead_id'] = lead.id
            result['subject'] = f"Quote Request for {lead.name}"
            result['body'] = (
                f"Dear Underwriter,<br/><br/>"
                f"Please submit your quote for {lead.name} by {lead.rfq_deadline or 'the specified deadline'}.<br/>"
                f"The risk note with benefit details is attached.<br/><br/>"
                f"Regards,<br/>{lead.bd_handler_id.name or self.env.user.name}"
            )
            result['underwriter_ids'] = [(6, 0, self.env['res.partner'].search([('is_insurer', '=', True)]).ids)]
        return result

    def action_send_emails(self):
        self.ensure_one()
        if not self.underwriter_ids:
            raise ValidationError("At least one underwriter must be selected.")
        if not self.lead_id.risk_note_document:
            raise ValidationError("A risk note document is required to send quote requests.")
        # Create lead.quote records
        quotes = self.env['lead.quote']
        attachment = False
        if self.lead_id.risk_note_document:
            try:
                attachment = self.env['ir.attachment'].create({
                    'name': self.lead_id.risk_note_document_filename or 'Risk_Note.pdf',
                    'datas': self.lead_id.risk_note_document,
                    'res_model': 'crm.lead',
                    'res_id': self.lead_id.id,
                    'type': 'binary',
                })
                _logger.info("Attachment created: ID %s, Name %s", attachment.id, attachment.name)
            except Exception as e:
                _logger.error("Failed to create attachment: %s", str(e))
                raise ValidationError("Failed to create attachment for risk note document.")
        for underwriter in self.underwriter_ids:
            quote = self.env['lead.quote'].create({
                'lead_id': self.lead_id.id,
                'partner_id': underwriter.id,
                'state': 'submitted',
            })
            quotes |= quote
        # Send emails
        template = self.env.ref('insurance_management.email_template_quote_request')
        for quote in quotes:
            portal_link = f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/innovus/quote/upload/{quote.access_token}"
            email_values = {
                'recipient_ids': [(6, 0, self.underwriter_ids.ids)],
            }
            if attachment:
                email_values['attachment_ids'] = [(4, attachment.id)]
            _logger.info("Sending email for quote ID %s, partner %s, portal_link %s", quote.id, quote.partner_id.name, portal_link)
            template.with_context(portal_link=portal_link).send_mail(
                quote.id,
                force_send=True,
                email_values=email_values
            )
        # Notify BD handler
        bd_handler = self.lead_id.bd_handler_id or self.env.user
        self.lead_id.message_post(
            body="Quote request emails sent to underwriters.",
            message_type='notification',
            partner_ids=[bd_handler.partner_id.id]
        )
        return {'type': 'ir.actions.act_window_close'}