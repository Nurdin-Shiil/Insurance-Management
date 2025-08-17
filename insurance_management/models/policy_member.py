from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
import logging


_logger = logging.getLogger(__name__)


class InsurancePolicyMember(models.Model):
    _name = 'insurance.policy.member'
    _description = 'Insurance Policy Member'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Member Name', required=True, track_visibility='onchange')
    id_no = fields.Char(string='ID Number')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    age = fields.Integer(string='Age', required=True)
    dependent_count = fields.Integer(string='Dependent Count', compute='_compute_dependent_count', store=True, help='Number of dependents, including newborns.')
    band_label = fields.Char(string='Band Label', compute='_compute_band_label', inverse='_inverse_band_label', store=True)
    premium = fields.Float(string='Premium', compute='_compute_premium', store=True, digits=(16, 2))
    locked_premium = fields.Float(string='Locked Premium', readonly=True, digits=(16, 2), help='Premium set at invoice creation, used for active members.')
    currency_id = fields.Many2one('res.currency', related='policy_id.insurer_id.currency_id', readonly=True)
    state = fields.Selection([('pending', 'Pending'), ('active', 'Active'), ('deleted', 'Deleted')], default='pending', track_visibility='onchange')
    policy_id = fields.Many2one('insurance.policy', string='Policy')
    deleted_policy_id = fields.Many2one('insurance.policy', string='Deleted From Policy')
    deletion_date = fields.Datetime(string='Deletion Date', readonly=True)
    creation_date = fields.Datetime(string='Creation Date', readonly=True, help='Date when the member transitioned to Active state')
    partner_id = fields.Many2one('res.partner', string='Contact', domain=[('is_insurer', '=', False)], help='Linked contact for this member')
    invoice_line_ids = fields.One2many('account.move.line', 'insurance_policy_member_id', string='Invoice Lines', readonly=True)
    activation_date = fields.Datetime(string='Activation Date', )
    principal_member_id = fields.Many2one('insurance.policy.member', string='Principal Member', domain="[('policy_id', '=', policy_id), ('id', '!=', id)]", help='The principal member this record is linked to, if a dependent.')
    linked_dependent_ids = fields.One2many('insurance.policy.member', 'principal_member_id', string='Linked Dependents', domain="[('state', '!=', 'deleted')]", help='Members linked to this principal member.')
    relation_type = fields.Selection([
        ('principal', 'Principal'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('newborn', 'Newborn'),
        ('other', 'Other'),
    ], string='Relation Type', default='principal', required=True)
    is_newborn = fields.Boolean(string='Is Newborn', compute='_compute_is_newborn', store=True)
    initially_active = fields.Boolean(compute='_compute_change_flags', store=False)
    added_after_activation = fields.Boolean(compute='_compute_change_flags', store=False)
    deleted_in_period = fields.Boolean(compute='_compute_change_flags', store=False)


    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], string='Gender')
    date_of_birth = fields.Date(string='Date of Birth')
    unique_identifier = fields.Char(string='Unique Identifier', required=True)

    @api.depends('relation_type')
    def _compute_is_newborn(self):
        for member in self:
            member.is_newborn = member.relation_type == 'newborn'

    @api.constrains('age', 'relation_type', 'principal_member_id')
    def _check_age_and_relation(self):
        for member in self:
            if member.age < 0:
                raise UserError('Age cannot be negative.')
            if member.relation_type == 'newborn' and member.age > 1:
                raise UserError('Newborn members must be 1 year old or younger.')
            if member.principal_member_id and member.relation_type == 'principal':
                raise UserError('A member with a principal member cannot have relation type "Principal".')
            if not member.principal_member_id and member.relation_type != 'principal':
                raise UserError('A member without a principal member must have relation type "Principal".')
            if member.date_of_birth and (fields.Date.today() - member.date_of_birth).days < 0:
                raise UserError('Date of birth cannot be in the future.')

    def handle_newborn_activity_change(self):
        for member in self:
            newborns = member.linked_dependent_ids.filtered(lambda d: d.relation_type == 'newborn')
            if newborns:
                member._create_or_update_newborn_activity()
            else:
                member._cancel_newborn_activity()

    def _create_or_update_newborn_activity(self):
        self.ensure_one()
        care_team_user = self.env.ref('base.user_admin')
        summary = f"Send newborn package for member {self.name}"
        note = (
            f"Newborn dependent(s) have been added for member **{self.name}** "
            f"under policy **{self.policy_id.name}**.\n\n"
            f"Prepare and deliver the newborn package."
        )
        existing_activity = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('summary', 'ilike', 'Send newborn package'),
        ], limit=1)
        if not existing_activity:
            self.activity_schedule(
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                summary=summary,
                note=note,
                user_id=care_team_user.id
            )

    def _cancel_newborn_activity(self):
        self.ensure_one()
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('summary', 'ilike', 'Send newborn package')
        ])
        activities.unlink()

    def _compute_change_flags(self):
        for member in self:
            policy_activation = member.policy_id.active_date or False
            if not policy_activation:
                member.initially_active = False
                member.added_after_activation = False
            else:
                member.initially_active = (
                    member.activation_date
                    and member.activation_date <= policy_activation + timedelta(seconds=1)
                )
                member.added_after_activation = (
                    member.creation_date
                    and member.creation_date > policy_activation + timedelta(seconds=1)
                )
                member.deleted_in_period = (
                    member.state == 'deleted'
                    and self._context.get('start_dt') and self._context.get('end_dt')
                    and self._context['start_dt'] <= member.deletion_date <= self._context['end_dt']
                )

    @api.depends('linked_dependent_ids', 'linked_dependent_ids.state')
    def _compute_dependent_count(self):
        for member in self:
            member.dependent_count = len(member.linked_dependent_ids.filtered(lambda d: d.state != 'deleted'))

    @api.depends('dependent_count', 'principal_member_id')
    def _compute_band_label(self):
        for member in self:
            if member.principal_member_id:
                member.band_label = False
            else:
                total_count = 1 + member.dependent_count
                member.band_label = 'M' if total_count == 1 else f'M+{total_count - 1}'

    def _inverse_band_label(self):
        for member in self:
            if member.principal_member_id:
                continue
            if member.band_label:
                if member.band_label.lower() == 'm':
                    member.dependent_count = 0
                elif member.band_label.lower().startswith('m+'):
                    try:
                        member.dependent_count = int(member.band_label[2:])
                    except ValueError:
                        member.dependent_count = 0
                else:
                    member.dependent_count = 0
            else:
                member.dependent_count = 0

    @api.depends('dependent_count', 'policy_id.rate_table_id', 'deleted_policy_id.rate_table_id', 'principal_member_id', 'creation_date', 'policy_id.end_date', 'deleted_policy_id.end_date', 'state', 'invoice_line_ids')
    def _compute_premium(self):
        for member in self:
            # Determine policy and rate table
            policy = member.policy_id or member.deleted_policy_id
            rate_table = policy.rate_table_id if policy else False
            if not rate_table or not hasattr(rate_table, 'get_inpatient_premium') or not hasattr(rate_table, 'get_outpatient_premium'):
                member.premium = 0.0
                continue

            # Get policy dates
            active_date = policy.active_date
            end_date = policy.end_date

            # Calculate full premium
            if not member.principal_member_id:
                # Principal member: Use base 'M' premium
                full_premium = (
                    rate_table.get_inpatient_premium(0) +
                    rate_table.get_outpatient_premium(0)
                )
            else:
                # Dependent: Calculate premium as difference between bands
                principal = member.principal_member_id
                dependent_count = len(principal.linked_dependent_ids.filtered(lambda d: d.state != 'deleted'))
                if dependent_count == 1:
                    # First dependent: M+1 - M
                    full_premium = (
                        (rate_table.get_inpatient_premium(1) - rate_table.get_inpatient_premium(0)) +
                        (rate_table.get_outpatient_premium(1) - rate_table.get_outpatient_premium(0))
                    )
                else:
                    # Subsequent dependent: M+n - M+(n-1)
                    full_premium = (
                        (rate_table.get_inpatient_premium(dependent_count - 1) - rate_table.get_inpatient_premium(dependent_count - 2)) +
                        (rate_table.get_outpatient_premium(dependent_count - 1) - rate_table.get_outpatient_premium(dependent_count - 2))
                    )

            # Prorate premium
            if policy.state == 'active' and active_date and end_date:
                # Convert end_date (Date) to Datetime for calculation
                end_datetime = datetime.combine(end_date, datetime.min.time())
                total_days = (end_datetime - active_date).days
                if total_days <= 0:
                    member.premium = 0.0
                    continue

                if member.state == 'active' and member.locked_premium:
                    # Use locked premium from invoice creation
                    member.premium = member.locked_premium
                elif member.state == 'pending' and member.added_after_activation:
                    # Prorate from creation_date for pending members
                    start_date = member.creation_date or fields.Datetime.now()
                    if start_date > end_datetime:
                        member.premium = 0.0
                    else:
                        covered_days = (end_datetime - start_date).days
                        if covered_days > 0:
                            proration_ratio = covered_days / total_days
                            member.premium = full_premium * proration_ratio
                        else:
                            member.premium = 0.0
                else:
                    # Full premium for initially active or deleted members
                    member.premium = full_premium
            else:
                # Full premium for non-active policy or missing dates
                member.premium = full_premium

    @api.model
    def create(self, vals):
        if not vals.get('partner_id'):
            partner = False
            if vals.get('id_no') or vals.get('email') or vals.get('phone'):
                domain = []
                if vals.get('id_no'):
                    domain.append(('id_no', '=', vals['id_no']))
                if vals.get('email'):
                    domain.append(('email', '=', vals['email']))
                if vals.get('phone'):
                    domain.append(('phone', '=', vals['phone']))
                if domain:
                    partner = self.env['res.partner'].search(domain, limit=1)
                if not partner:
                    partner_vals = {
                        'name': vals.get('name', 'New Contact'),
                        'id_no': vals.get('id_no', False),
                        'email': vals.get('email', False),
                        'phone': vals.get('phone', False),
                        'is_insurer': False,
                    }
                    partner = self.env['res.partner'].create(partner_vals)
                vals['partner_id'] = partner.id
        if not vals.get('creation_date'):
            vals['creation_date'] = fields.Datetime.now()
        if vals.get('state') == 'active' and not vals.get('activation_date'):
            vals['activation_date'] = fields.Datetime.now()
        return super(InsurancePolicyMember, self).create(vals)

    def write(self, vals):
        for member in self:
            if 'state' in vals and vals['state'] == 'active' and member.state == 'pending' and not member.creation_date:
                vals['creation_date'] = fields.Datetime.now()
        return super(InsurancePolicyMember, self).write(vals)

    def unlink(self):
        for member in self:
            principal = member.principal_member_id
            if member.state == 'active' and member.policy_id and member.policy_id.state == 'active' and (member.premium or member.locked_premium):
                # Set state to deleted before creating credit note
                member.write({
                    'state': 'deleted',
                    'deletion_date': fields.Datetime.now(),
                })
                result = member.policy_id._create_credit_note_for_member(member)
                if not result:
                    _logger.info(f"No credit note created for member {member.name}. Proceeding with deletion.")
            else:
                member.write({
                    'state': 'deleted',
                    'deletion_date': fields.Datetime.now(),
                })
            member.write({
                'policy_id': False,
                'deleted_policy_id': member.policy_id.id,
            })
            if principal:
                principal._compute_dependent_count()
                principal._compute_band_label()

    def action_view_activities(self):
        self.ensure_one()
        return {
            'name': 'Activities',
            'type': 'ir.actions.act_window',
            'res_model': 'mail.activity',
            'view_mode': 'list,form',
            'domain': [
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
            'target': 'current',
        }