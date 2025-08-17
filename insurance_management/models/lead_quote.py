# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import uuid
from datetime import timedelta

class LeadQuote(models.Model):
    _name = 'lead.quote'
    _description = 'Underwriter Quote'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner',
        string='Underwriter',
        required=True,
        domain=[('is_insurer', '=', True)]
    )
    quote_document = fields.Binary(string='Quote Document')
    quote_document_filename = fields.Char(string='Quote Filename')
    premium_amount = fields.Float(string='Premium Amount', digits='Product Price')
    coverage_terms = fields.Text(string='Coverage Terms')
    state = fields.Selection([
        ('submitted', 'Submitted'),
        ('negotiating', 'Negotiating'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected')
    ], string='Status', default='submitted', tracking=True)
    submission_date = fields.Date(string='Submission Date', default=fields.Date.today)
    comments = fields.Text(string='Comments')
    access_token = fields.Char(string='Access Token', readonly=True, copy=False)
    token_expiry = fields.Date(string='Token Expiry', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('access_token'):
                vals['access_token'] = str(uuid.uuid4())
                vals['token_expiry'] = fields.Date.today() + timedelta(days=7)
        return super().create(vals_list)

    def action_confirm(self):
        """Confirm this quote and reject others for the same lead."""
        self.ensure_one()
        if self.state not in ['submitted', 'negotiating']:
            raise ValidationError("Only Submitted or Negotiating quotes can be confirmed.")
        self.write({'state': 'confirmed'})
        other_quotes = self.env['lead.quote'].search([
            ('lead_id', '=', self.lead_id.id),
            ('id', '!=', self.id),
            ('state', 'in', ['submitted', 'negotiating'])
        ])
        other_quotes.write({'state': 'rejected'})
        self.message_post(body=f"Quote confirmed for underwriter {self.partner_id.name}.")

    def action_negotiate(self):
        """Set quote to Negotiating."""
        self.ensure_one()
        if self.state != 'submitted':
            raise ValidationError("Only Submitted quotes can be set to Negotiating.")
        self.write({'state': 'negotiating'})
        self.message_post(body="Quote set to Negotiating.")

    def action_reject(self):
        """Reject this quote."""
        self.ensure_one()
        if self.state == 'confirmed':
            raise ValidationError("Cannot reject a Confirmed quote.")
        self.write({'state': 'rejected'})
        self.message_post(body="Quote rejected.")