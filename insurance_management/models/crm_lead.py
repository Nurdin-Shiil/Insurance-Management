# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.translate import _
from datetime import datetime, timedelta
import base64
from io import BytesIO
import logging

import logging

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    product_id = fields.Many2one(
        "product.product",
        string="Policy Product",
        domain=[("type", "=", "service")],
        help="Product used for invoices and credit notes of policies linked to this lead.",
    )

    rate_table_id = fields.Many2one("insurance.rate.table")

    lead_population_ids = fields.One2many(
        comodel_name="crm.lead.population",
        inverse_name="lead_id",
        string="Lead Population",
        copy=True,
        help="Track the population details for this lead, including dependents and family count.",
    )

    underwriter_id = fields.Many2one("res.partner", string="Underwriter")
    medical_benefit_ids = fields.One2many("medical.benefit", "lead_id")
    policy_id = fields.Many2one("insurance.policy", string="Related Policy")

    product_id = fields.Many2one(
        "product.product",
        string="Policy Product",
        domain=[("type", "=", "service")],
        help="Product used for invoices and credit notes of policies linked to this lead.",
    )

    lead_population_ids = fields.One2many(
        comodel_name="crm.lead.population",
        inverse_name="lead_id",
        string="Lead Population",
        copy=True,
        help="Track the population details for this lead, including dependents and family count.",
    )
    special_exclusion = fields.Text(string='Exclusions')

    def action_compute_premiums(self):
        """
        Compute premiums for the lead based on the associated rate table.
        This method should be overridden to implement the actual premium calculation logic.
        """
        for lead in self:
            if lead.rate_table_id:
                _logger.info(
                    "Computing premiums for lead %s using rate table %s",
                    lead.id,
                    lead.rate_table_id.id,
                )

    def action_benefits(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/report/pdf/medical_benefit/%s" % self.id,
        }

    def action_create_policy(self):
        self.ensure_one()
        if not self.underwriter_id:
            raise UserError("An Underwriter/Insurer must be selected")
        if not self.medical_benefit_ids:
            raise UserError("Please select benefits")
        policy = self.env["insurance.policy"].create(
            {
                "lead_id": self.id,
                "insurer_id": self.underwriter_id.id,
                "partner_id": self.partner_id.id,
                "rate_table_id": self.medical_benefit_ids[
                    0
                ].benefit_id.rate_table_id.id,
            }
        )
        self.policy_id = policy.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Insurance Policy"),
            "res_model": "insurance.policy",
            "res_id": policy.id,
            "view_mode": "form",
        }

    def action_view_policy(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Insurance Policy"),
            "res_model": "insurance.policy",
            "res_id": self.policy_id.id,
            "view_mode": "form",
        }
        
        
    @api.onchange('medical_benefit_ids')
    def _onchange_exclusions(self):
        for lead in self:
            exclusion = []
            for benefit in lead.medical_benefit_ids:
                exclusion.append(benefit.benefit_id.special_exclusion or '')
            lead.special_exclusion = "\n".join(exclusion)



    # Fields for risk note and quote management
    rfq_deadline = fields.Date('RFQ Deadline')
    risk_note_document = fields.Binary(string='Risk Note Document')
    risk_note_document_filename = fields.Char(string='Risk Note Filename')
    quote_ids = fields.One2many('lead.quote', 'lead_id', string='Quotes')
    bd_handler_id = fields.Many2one('res.users', string='BD Handler')

    def action_generate_risk_note(self):
        """Generate risk note PDF and schedule RFQ deadline alert."""
        self.ensure_one()
        if not self.partner_id or not self.medical_benefit_ids:
            raise ValidationError(("Client and Medical Benefits are required to generate a risk note."))

        try:
            report = self.env.ref('insurance_management.action_report_risk_note')
        except ValueError:
            raise UserError(_("Risk note report is not configured. Please ensure the report is installed."))

        # Generate PDF
        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(report.report_name, res_ids=[self.id])
        self.risk_note_document = base64.b64encode(pdf_content)
        self.risk_note_document_filename = f"Risk_Note_{self.name}_{fields.Date.today()}.pdf"

        # Ensure RFQ deadline
        if not self.rfq_deadline:
            self.rfq_deadline = fields.Date.today() + timedelta(days=30)

        # Schedule alert
        deadline = fields.Date.from_string(self.rfq_deadline) - timedelta(days=7)
        if deadline >= fields.Date.today():
            self.env['mail.activity'].create({
                'res_model_id': self.env['ir.model']._get('crm.lead').id,
                'res_id': self.id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': 'RFQ Deadline Reminder',
                'note': f"RFQ deadline for lead {self.name} is approaching on {self.rfq_deadline}.",
                'date_deadline': deadline,
                'user_id': self.bd_handler_id.id or self.env.user.id,
            })

        return True

    def action_send_quote_request(self):
        """Send quote request emails with upload links to underwriters."""
        self.ensure_one()
        if not self.risk_note_document:
            raise ValidationError(("Risk note document is required to send quote requests."))

        # Get underwriters
        underwriters = self.env['res.partner'].search([('is_insurer', '=', True), ('email', '!=', False)])
        if not underwriters:
            raise ValidationError(("No underwriters with valid email addresses found. Please configure underwriters in Contacts."))

        template = self.env.ref('insurance_management.email_template_quote_request')
        for underwriter in underwriters:
            # Create a quote record with token
            quote = self.env['lead.quote'].create({
                'lead_id': self.id,
                'partner_id': underwriter.id,
                'state': 'submitted',
            })
            # Send email with upload link
            upload_url = f"{self.get_base_url()}/innovus/quote/upload/{quote.access_token}"
            template.with_context(
                upload_url=upload_url,
                underwriter_name=underwriter.name
            ).send_mail(
                self.id,
                force_send=True,
                email_values={
                    'email_to': underwriter.email,
                    'attachment_ids': [(0, 0, {
                        'name': self.risk_note_document_filename,
                        'datas': self.risk_note_document,
                        'mimetype': 'application/pdf'
                    })]
                }
            )
        self.message_post(body=_("Quote requests sent to %s underwriters.") % len(underwriters))

    @api.model
    def _cron_rfq_deadline_alerts(self):
        """Send RFQ deadline reminders."""
        today = fields.Date.today()
        alerts = self.search([('rfq_deadline', '!=', False)])
        for lead in alerts:
            if lead.rfq_deadline:
                days_left = (lead.rfq_deadline - today).days
                if days_left in [5, 4, 3, 1]:
                    template = self.env.ref('insurance_management.email_template_rfq_alert')
                    template.send_mail(lead.id, force_send=True)