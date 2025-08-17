# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    id_no = fields.Char(string='ID Number')

    is_insurer = fields.Boolean(string='Is an Insurer')
    rate_table_ids = fields.One2many(
        comodel_name='insurance.rate.table',
        inverse_name='insurer_id',
        string='Rate Tables'
    )