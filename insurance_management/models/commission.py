from odoo import models, fields, api
import logging
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)

class InsuranceCommissionPlan(models.Model):
    _name = 'insurance.commission.plan'
    _description = 'Insurance Commission Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Plan Name', required=True)
    commission_rate = fields.Float(string='Commission Rate (%)', required=True, digits=(5, 2), help='Percentage of invoice amount to be paid as commission.')
    policy_ids = fields.One2many('insurance.policy', 'commission_plan_id', string='Policies', readonly=True)
    policy_count = fields.Integer(string='Policy Count', compute='_compute_policy_count', store=True)

    @api.depends('policy_ids')
    def _compute_policy_count(self):
        for plan in self:
            plan.policy_count = len(plan.policy_ids)

    @api.constrains('commission_rate')
    def _check_commission_rate(self):
        for rec in self:
            if rec.commission_rate > 100:
                raise ValidationError("Commission rate cannot exceed 100%.")
            if rec.commission_rate < 0:
                raise ValidationError("Commission rate must be a positive number.")

    def action_view_policies(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'insurance.policy',
            'view_mode': 'list,form',
            'domain': [('commission_plan_id', '=', self.id)],
            'context': {'default_commission_plan_id': self.id},
            'target': 'current',
            'name': f'Policies for {self.name}',
        }
    

class InsuranceCommission(models.Model):
    _name = 'insurance.commission'
    _description = 'Insurance Commission'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    commission_plan_id = fields.Many2one('insurance.commission.plan', string='Commission Plan', required=True, readonly=True)
    policy_id = fields.Many2one('insurance.policy', string='Policy', required=True, readonly=True)
    invoice_id = fields.Many2one('account.move', string='Source Invoice', required=True, readonly=True, domain=[('move_type', '=', 'out_invoice')])
    commission_date = fields.Date(string='Commission Date', required=True, readonly=True, default=fields.Date.today)
    commission_amount = fields.Float(string='Commission Achieved', readonly=True, digits=(16, 2))
    currency_id = fields.Many2one('res.currency', related='policy_id.insurer_id.currency_id', readonly=True)