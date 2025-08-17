from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BenefitS(models.Model):
    _name = "benefit"
    _description = "Benefits"

    name = fields.Char()
    medical_benefit_id = fields.Many2one("medical.benefit")
    special_exclusion = fields.Text("Exclusions")
    rate_table_id = fields.Many2one("insurance.rate.table", string='Rate Table')
    benefit_line_ids = fields.One2many("benefit.line", "benefit_id")


class BenefitLines(models.Model):
    _name = "benefit.line"
    _description = "Benefit Lines"

    benefit_id = fields.Many2one("benefit")
    benefit = fields.Char(string='Benefit')
    benefit_scope_ids = fields.One2many("benefit.scope", "benefit_line_id")
    benefit_limit = fields.Char("Benefit Limit")
    scope = fields.Char(string="Scope")
    type = fields.Char(string="Type")
    admin = fields.Char(string="Admin")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s - %s - %s" % (
                rec.benefit,
                rec.benefit_limit,
                rec.scope,
            )


class BenefitScope(models.Model):
    _name = "benefit.scope"
    _description = "Benefit Scope"

    benefit_line_id = fields.Many2one("benefit.line")
    name = fields.Char(string="Benefit")
    limit = fields.Text(string="Limits")
    scope = fields.Char(string="Scope")
