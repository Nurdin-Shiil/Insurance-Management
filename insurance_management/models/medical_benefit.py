from odoo import models, fields, api


class MedicalBenefit(models.Model):
    _name = "medical.benefit"
    _description = "Medical Benefits"
    
    lead_id = fields.Many2one('crm.lead')
    benefit_id = fields.Many2one('benefit')
