from odoo import models, fields, api

class InsuranceRateTableBand(models.Model):
    _name = 'insurance.rate.table.band'
    _description = 'Premium Band (M, M+1, …)'

    rate_table_id = fields.Many2one('insurance.rate.table', string='Rate Table', required=True, ondelete='cascade')
    dependent_count = fields.Integer(string='# Dependents', required=True, help='0→M, 1→M+1,…')
    band_label = fields.Char(string='Band', compute='_compute_band_label', store=True)
    inpatient_premium = fields.Monetary(string='Inpatient Premium', required=True)
    outpatient_premium = fields.Monetary(string='Outpatient Premium', required=True)
    currency_id = fields.Many2one('res.currency', related='rate_table_id.currency_id', readonly=True)

    @api.depends('dependent_count')
    def _compute_band_label(self):
        for rec in self:
            rec.band_label = 'M' if rec.dependent_count == 0 else f'M+{rec.dependent_count}'

    _sql_constraints = [
        ('unique_band_per_table', 'unique(rate_table_id, dependent_count)', 'Each dependent count band must be unique per table.'),
        ('check_nonnegative', 'CHECK(dependent_count >= 0)', 'Dependent count must be non-negative.'),
    ]