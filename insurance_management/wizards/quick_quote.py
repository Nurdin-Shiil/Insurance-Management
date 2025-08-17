from odoo import models, fields, api

class QuickQuote(models.TransientModel):
    _name = 'insurance.quick.quote'
    _description = 'Quick Quote Wizard'

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    currency_id = fields.Many2one('res.currency')
    insurer_id = fields.Many2one('res.partner', string='Insurer', domain=[('is_insurer','=',True)], required=True)
    dependent_count = fields.Integer(string='Dependent Count', required=True, help='0→M,1→M+1…')
    inpatient_premium = fields.Monetary(string='Inpatient Premium', readonly=True)
    outpatient_premium = fields.Monetary(string='Outpatient Premium', readonly=True)
    total_premium = fields.Monetary(string='Total Premium', readonly=True)

    @api.onchange('insurer_id', 'dependent_count')
    def _onchange_compute_premium(self):
        for rec in self:
            rec.inpatient_premium = rec.outpatient_premium = rec.total_premium = 0
            if rec.insurer_id:
                rt = self.env['insurance.rate.table'].search([('insurer_id','=',rec.insurer_id.id)], limit=1)
                band = rt.band_ids.filtered(lambda b: b.dependent_count == rec.dependent_count)[:1]
                if band:
                    rec.inpatient_premium = band.inpatient_premium
                    rec.outpatient_premium = band.outpatient_premium
                    rec.total_premium = band.inpatient_premium + band.outpatient_premium

    def action_print_quote(self):
        return self.env.ref('insurance_underwriting.action_report_insurance_quote').report_action(self)