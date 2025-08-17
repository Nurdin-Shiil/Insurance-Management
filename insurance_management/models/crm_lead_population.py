# -*- coding: utf-8 -*-
from odoo import models, fields,api


class CrmLeadPopulation(models.Model):
    """Model to track lead population details such as dependents and family count."""
    _name = 'crm.lead.population'
    _description = 'Lead Population'
    lead_id = fields.Many2one('crm.lead')
    dependent_count = fields.Integer(default=0)
    family_count = fields.Integer(default=0)
    inpatient_premium = fields.Float(default=0.0,compute='_compute_inpatient_premium')
    outpatient_premium = fields.Float(default=0.0,compute='_compute_outpatient_premium')
    band_total = fields.Float(default=0.0, compute='_compute_band_total')
    band_label = fields.Char(string='Band', compute='_compute_band_label', store=True)

    @api.depends('dependent_count')
    def _compute_band_label(self):
        """Compute the band label based on the dependent count."""
        for rec in self:
            rec.band_label = 'M' if rec.dependent_count == 0 else f'M+{rec.dependent_count}'


    @api.depends('lead_id')
    def _compute_inpatient_premium(self):
        """Compute inpatient premium based on dependent count."""
        rate_table_id = self.lead_id.rate_table_id
        if rate_table_id:
            for rec in self:
                rec.inpatient_premium = rate_table_id.get_inpatient_premium(rec.dependent_count)*rec.family_count

    @api.depends('lead_id')
    def _compute_outpatient_premium(self):
        """Compute outpatient premium based on dependent count."""
        rate_table_id = self.lead_id.rate_table_id
        if rate_table_id:
            for rec in self:
                rec.outpatient_premium = rate_table_id.get_outpatient_premium(rec.dependent_count)*rec.family_count

    @api.depends('inpatient_premium', 'outpatient_premium')
    def _compute_band_total(self):
        """Compute the total premium for the band."""
        for rec in self:
            rec.band_total = rec.inpatient_premium + rec.outpatient_premium