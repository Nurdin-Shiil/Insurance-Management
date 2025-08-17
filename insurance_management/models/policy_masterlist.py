from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
from io import BytesIO
import xlsxwriter
from dateutil.relativedelta import relativedelta

class InsurancePolicyMasterlist(models.Model):
    _name = 'insurance.policy.masterlist'
    _description = 'Insurance Policy Masterlist'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    policy_id = fields.Many2one('insurance.policy', string='Policy', required=True, ondelete='cascade')
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    # Computed fields for the four categories
    initial_member_ids = fields.One2many('insurance.policy.member', compute='_compute_members', string='Initial Members')
    addition_member_ids = fields.One2many('insurance.policy.member', compute='_compute_members', string='Additions')
    deletion_member_ids = fields.One2many('insurance.policy.member', compute='_compute_members', string='Deletions')
    active_member_ids = fields.One2many('insurance.policy.member', compute='_compute_members', string='Active Members')

    @api.depends('policy_id')
    def _compute_name(self):
        for record in self:
            record.name = f"Masterlist for {record.policy_id.name}" if record.policy_id else "Masterlist"

    @api.depends('policy_id', 'policy_id.member_ids', 'policy_id.deleted_ids')
    def _compute_members(self):
        for record in self:
            if not record.policy_id:
                record.initial_member_ids = [(5, 0, 0)]
                record.addition_member_ids = [(5, 0, 0)]
                record.deletion_member_ids = [(5, 0, 0)]
                record.active_member_ids = [(5, 0, 0)]
                return

            policy_activation = record.policy_id.active_date or False
            all_members = record.policy_id.member_ids | record.policy_id.deleted_ids

            # Initial Members: Members with activation_date same as policy activation date
            initial_members = all_members.filtered(
                lambda m: m.activation_date and policy_activation and
                m.activation_date <= policy_activation + relativedelta(seconds=1)
            )

            # Additions: Members added after policy activation
            addition_members = all_members.filtered(
                lambda m: m.activation_date and policy_activation and
                m.activation_date > policy_activation + relativedelta(seconds=1)
            )

            # Deletions: Members with state 'deleted'
            deletion_members = all_members.filtered(lambda m: m.state == 'deleted')

            # Active Members: Members with state 'active'
            active_members = record.policy_id.member_ids.filtered(lambda m: m.state == 'active')

            record.initial_member_ids = [(6, 0, initial_members.ids)]
            record.addition_member_ids = [(6, 0, addition_members.ids)]
            record.deletion_member_ids = [(6, 0, deletion_members.ids)]
            record.active_member_ids = [(6, 0, active_members.ids)]

    def action_export_excel(self, category=None):
        """Export the specified category to an Excel file."""
        self.ensure_one()

        # Fetch category from context if not passed as argument
        if not category:
            category = self.env.context.get('category')
            if not category or category not in ['initial', 'additions', 'deletions', 'active']:
                raise UserError("No valid category specified for export. Please select a valid category (Initial Members, Additions, Deletions, or Active Members).")

        # Map category to field and report name
        category_map = {
            'initial': ('initial_member_ids', 'Initial Members'),
            'additions': ('addition_member_ids', 'Additions'),
            'deletions': ('deletion_member_ids', 'Deletions'),
            'active': ('active_member_ids', 'Active Members'),
        }
        member_field, report_name = category_map[category]
        members = self[member_field]

        if not members:
            raise UserError(f"No members found in the {report_name} category.")

        # Prepare data for Excel, including new fields
        data = [{
            'Principal Member': member.principal_member_id.name or '',
            'Relation Type': member.relation_type,
            'Name': member.name,
            'Contact': member.partner_id.name or '',
            'ID Number': member.id_no or '',
            'Email': member.email or '',
            'Phone': member.phone or '',
            'Age': member.age,
            'Band Label': member.band_label or '',
            'Premium': member.premium,
            'State': member.state,
            'Activation Date': member.activation_date.strftime('%Y-%m-%d %H:%M:%S') if member.activation_date else '',
            'Deletion Date': member.deletion_date.strftime('%Y-%m-%d %H:%M:%S') if member.deletion_date else '',
        } for member in members]

        # Generate Excel file
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet(report_name)

        # Define header format (bold, centered)
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
        cell_format = workbook.add_format({'text_wrap': True, 'border': 1})

        # Headers
        headers = [
            'Principal Member', 'Relation Type', 'Name', 'Contact', 'ID Number', 'Email',
            'Phone', 'Age', 'Band Label', 'Premium', 'State', 'Activation Date', 'Deletion Date'
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
            # Optionally set initial width based on header length
            worksheet.set_column(col, col, len(header) + 5)

        # Write data rows with cell format
        for row, record in enumerate(data, start=1):
            for col, key in enumerate(headers):
                value = record.get(key, '')
                worksheet.write(row, col, value, cell_format)

        workbook.close()
        output.seek(0)

        # Create report action
        report = self.env['ir.attachment'].create({
            'name': f"{self.policy_id.name}_{report_name.replace(' ', '_')}.xlsx",
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{report.id}?download=true',
            'target': 'self',
        }