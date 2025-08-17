# -*- coding: utf-8 -*-
from odoo import models, fields

class InsuranceRateTable(models.Model):
    _name = 'insurance.rate.table'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Insurance Rate Table (per insurer & plan)'

    name = fields.Char(string='Table Name', required=True)
    insurer_id = fields.Many2one('res.partner', string='Insurer', domain=[('is_insurer','=',True)], required=True)
    plan_code = fields.Char(string='Plan Code', required=True)

    outpatient_limit = fields.Monetary(string='Outpatient Limit', required=True)
    outpatient_limit_type = fields.Selection(
        [('family', 'Per family'), ('person', 'Per Person')],
        string='Outpatient Limit Type',
        required=True,
        default='family',
    )
    outpatient_limit_scope = fields.Selection(
        [('standalone', 'Standalone'), ('premium', 'Premium')],
        string='Outpatient Limit Scope',
        required=True,
        default='standalone',
    )
    outpatient_limit_admin = fields.Selection([
        ('insured', 'Insured'), ('funded', 'Funded')],
        string='Outpatient Limit Admin',
        required=True,
        default='insured'
    )

    inpatient_limit_type = fields.Selection(
        [('family', 'Per family'), ('person', 'Per Person')],
        string='Inpatient Limit Type',
        required=True,
        default='family',
    )
    inpatient_limit_scope = fields.Selection(
        [('standalone', 'Standalone'), ('premium', 'Premium')],
        string='Inpatient Limit Scope',
        required=True,
        default='standalone',
    )
    inpatient_limit_admin = fields.Selection([
        ('insured', 'Insured'), ('funded', 'Funded')],
        string='Inpatient Limit Admin',
        required=True,
        default='insured'
    )
    inpatient_limit = fields.Monetary(string='Inpatient Limit', required=True)
    outpatient_limit_upgrade_1 = fields.Monetary(string='Outpatient Limit Upgrade 1', required=True)
    outpatient_limit_upgrade_2 = fields.Monetary(string='Outpatient Premium Upgrade 2', required=True)

    currency_id = fields.Many2one('res.currency', related='insurer_id.company_id.currency_id', readonly=True)
    band_ids = fields.One2many('insurance.rate.table.band', 'rate_table_id', string='Premium Bands', copy=True)


    def get_inpatient_premium(self, dependent_count):
        """
        Get the inpatient premium based on the dependent count.
        This method should be overridden to implement the actual premium calculation logic.
        """
        for band in self.band_ids:
            if band.dependent_count == dependent_count:
                return band.inpatient_premium
        return 0.0

    def get_outpatient_premium(self, dependent_count):
        """
        Get the outpatient premium based on the dependent count.
        This method should be overridden to implement the actual premium calculation logic.
        """
        for band in self.band_ids:
            if band.dependent_count == dependent_count:
                return band.outpatient_premium
        return 0.0