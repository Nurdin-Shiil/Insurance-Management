from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
import pytz

_logger = logging.getLogger(__name__)

class InsurancePolicy(models.Model):
    _name = 'insurance.policy'
    _description = 'Insurance Policy'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Policy Number", required=True, copy=False, readonly=True, default='New')

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('insurance.policy') or 'New'
        return super(InsurancePolicy, self).create(vals)

    partner_id = fields.Many2one(
        "res.partner",
        string="Related Contact",
        required=True,
        domain=[("is_insurer", "=", False)],
    )
    insurer_id = fields.Many2one(
        "res.partner",
        string="Insurer",
        domain=[("is_insurer", "=", True)],
        required=True,
    )
    rate_table_id = fields.Many2one(
        "insurance.rate.table", string="Rate Table", required=True
    )
    payment_type = fields.Selection(
        [("broker", "Direct to Broker"), ("underwriter", "Direct to Underwriter")],
        string="Payment Type",
        required=True,
        default="broker",
    )
    member_ids = fields.One2many(
        "insurance.policy.member", "policy_id", string="Members"
    )
    deleted_ids = fields.One2many(
        "insurance.policy.member", "deleted_policy_id", string="Deleted Members"
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("cancelled", "Cancelled")],
        default="draft",
    )
    claim_id = fields.Many2one('medical.claim', string='Claim')
    active_date = fields.Datetime(string='Activation Date', help='Date when the policy was set to active.')
    invoice_ids = fields.One2many('account.move', 'insurance_policy_id', string='Invoices', readonly=True)
    end_date = fields.Date(string='Policy End Date', compute='_compute_end_date', store=True)
    policy_frequency = fields.Selection([
        ('annual', 'Annually'),
        ('monthly', 'Monthly'),
    ], string='Policy Frequency', default='annual', required=True)
    policy_duration_months = fields.Integer(
        string='Duration (Months)',
        default=12,
        help="Only applicable if frequency is Monthly"
    )


    commission_plan_id = fields.Many2one(
        'insurance.commission.plan',
        string='Commission Plan',
        required=True,
        help='The commission plan applied to this policy.'
    )
    commission_ids = fields.One2many('insurance.commission', 'policy_id', string='Commissions', readonly=True)
    total_commission = fields.Float(
        string='Total Commission',
        compute='_compute_total_commission',
        store=True,
        digits=(16, 2)
    )

    @api.depends('commission_ids.commission_amount')
    def _compute_total_commission(self):
        for policy in self:
            policy.total_commission = sum(policy.commission_ids.mapped('commission_amount'))

    def action_view_commissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'insurance.commission',
            'view_mode': 'list,form',
            'domain': [('policy_id', '=', self.id)],
            'context': {'default_policy_id': self.id},
            'target': 'current',
            'name': f'Commissions for {self.name}',
        }

    def action_achievement_detail(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'insurance.commission',
            'view_mode': 'list,form',
            'domain': [('policy_id', '=', self.id)],
            'context': {'default_policy_id': self.id},
            'target': 'current',
            'name': f'Commission Achievements for {self.name}',
        }

    @api.constrains('commission_plan_id')
    def _check_commission_plan(self):
        for policy in self:
            if not policy.commission_plan_id:
                raise ValidationError('A commission plan must be selected for the policy.')


    masterlist_id = fields.Many2one('insurance.policy.masterlist', string='Masterlist', compute='_compute_masterlist', store=True)
    
    @api.depends('name')
    def _compute_masterlist(self):
        for policy in self:
            masterlist = self.env['insurance.policy.masterlist'].search([('policy_id', '=', policy.id)], limit=1)
            if not masterlist:
                masterlist = self.env['insurance.policy.masterlist'].create({'policy_id': policy.id})
            policy.masterlist_id = masterlist.id

    def action_view_masterlist(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'insurance.policy.masterlist',
            'view_mode': 'form',
            'res_id': self.masterlist_id.id,
            'target': 'current',
        }

    @api.depends('active_date', 'policy_frequency', 'policy_duration_months')
    def _compute_end_date(self):
        for rec in self:
            if rec.active_date:
                if rec.policy_frequency == 'annual':
                    rec.end_date = rec.active_date + relativedelta(years=1)
                elif rec.policy_frequency == 'monthly':
                    rec.end_date = rec.active_date + relativedelta(months=rec.policy_duration_months or 1)
            else:
                rec.end_date = False

    @api.constrains("rate_table_id", "insurer_id")
    def _check_rate_table_insurer(self):
        for policy in self:
            if policy.rate_table_id and policy.insurer_id and policy.rate_table_id.insurer_id != policy.insurer_id:
                raise ValidationError("The rate table must belong to the selected insurer.")

    @api.constrains("state")
    def _check_member_state_on_cancelled(self):
        for policy in self:
            if policy.state == "cancelled":
                invalid_members = (policy.member_ids | policy.deleted_ids).filtered(lambda m: m.state)
                if invalid_members and not self.env.context.get("allow_cancel_state_change"):
                    raise ValidationError(
                        f"Cannot have member states in a cancelled policy. Invalid members: {', '.join(invalid_members.mapped('name'))}. "
                        "Member states must be empty in cancelled policies."
                    )

    def _sync_member_states(self):
        for policy in self:
            with self.env.cr.savepoint():
                if policy.state == "cancelled":
                    (policy.member_ids | policy.deleted_ids).with_context(allow_cancel_state_change=True).write({"state": False})
                    _logger.info(f"Policy {policy.name} cancelled: all member states set to False.")
                elif policy.payment_type == "underwriter":
                    policy.member_ids.write({
                        "state": "active" if policy.state == "active" else "pending",
                        "activation_date": fields.Datetime.now() if policy.state == "active" else False,
                    })
                    _logger.info(f"Policy {policy.name} (underwriter): member states set to {policy.state}.")
                elif policy.payment_type == "broker":
                    paid_invoice = self.env["account.move"].search([
                        ("insurance_policy_id", "=", policy.id),
                        ("move_type", "=", "out_invoice"),
                        ("payment_state", "=", "paid"),
                    ], limit=1)
                    if paid_invoice:
                        policy.write({
                            'state': 'active',
                            'active_date': fields.Datetime.now() if not policy.active_date else policy.active_date
                        })
                        pending_members = policy.member_ids.filtered(lambda m: m.state == 'pending')
                        pending_members.write({
                            'state': 'active',
                            'activation_date': fields.Datetime.now()
                        })
                        _logger.info(f'Policy {policy.name} set to active: paid invoice {paid_invoice.name} found. Updated {len(pending_members)} pending members.')
                    else:
                        policy.write({"state": "draft"})
                        policy.member_ids.write({"state": "pending", "activation_date": False})
                        _logger.info(f"Policy {policy.name} set to draft: no paid invoice found.")

    @api.onchange("state", "payment_type")
    def _onchange_state(self):
        self._sync_member_states()

    def action_import_members(self):
        self.ensure_one()
        return {
            "name": "Import Policy Members",
            "type": "ir.actions.act_window",
            "res_model": "insurance.import.members",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id, "active_model": "insurance.policy"},
        }

    def action_confirm(self):
        for policy in self:
            if policy.payment_type == "broker":
                raise UserError("Cannot confirm policy when payment is handled by the broker. Mark the invoice as paid to activate.")
            policy.write({"state": "active", "active_date": fields.Datetime.now()})
            policy._sync_member_states()

    def action_create_invoice(self):
        for policy in self:
            if policy.payment_type != 'broker':
                raise UserError('Invoicing is only allowed for policies with payment type "Direct to Broker".')
            if not policy.partner_id:
                raise UserError('No customer found. Ensure the policy has a valid Related Contact assigned.')
            if not policy.commission_plan_id:
                raise UserError('Cannot create invoice without a commission plan. Please select a commission plan.')
            
            account = self.env["account.account"].search([("account_type", "=", "income")], limit=1)
            if not account:
                raise UserError('No income account found. Configure an income account in Accounting > Configuration > Chart of Accounts.')
            lines = []
            members = policy.member_ids if policy.state == "draft" else policy.member_ids.filtered(lambda m: m.state == "pending")
            if not members:
                raise UserError('No members to invoice. Add members to the policy or ensure some members are in "Pending" state for active policies.')
            invoice_date = fields.Date.today()
            end_datetime = datetime.combine(policy.end_date, datetime.min.time()) if policy.end_date else False
            total_days = (end_datetime - policy.active_date).days if policy.active_date and end_datetime else 0

            total_premium = 0.0
            for m in members:
                if not m.premium:
                    raise UserError(f"Member {m.name} has no premium. Ensure the policy has a valid Rate Table configured.")
                full_premium = m.premium
                if m.state == 'pending' and m.added_after_activation and total_days > 0 and end_datetime:
                    covered_days = (end_datetime - datetime.combine(invoice_date, datetime.min.time())).days
                    if covered_days > 0:
                        proration_ratio = covered_days / total_days
                        m.locked_premium = full_premium / (m.creation_date and (end_datetime - m.creation_date).days / total_days or 1) * proration_ratio
                    else:
                        m.locked_premium = 0.0
                else:
                    m.locked_premium = full_premium
                total_premium += m.locked_premium
                lines.append(
                    (0, 0, {
                        "name": f"{policy.name} - Premium: {m.name} ({m.band_label or m.relation_type})",
                        "quantity": 1,
                        "price_unit": m.premium,
                        "account_id": account.id,
                        "insurance_policy_member_id": m.id,
                        "partner_id": m.partner_id.id if m.partner_id else policy.partner_id.id,
                    }),
                )

            invoice = self.env["account.move"].create({
                "move_type": "out_invoice",
                "partner_id": policy.partner_id.id,
                "invoice_line_ids": lines,
                "insurance_policy_id": policy.id,
                "invoice_date": invoice_date,
            })
            invoice.action_post()
            _logger.info(f"Invoice {invoice.name} created for policy {policy.name} with {len(lines)} lines.")
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': invoice.id,
                'target': 'current',
            }

    def _create_credit_note_for_member(self, member):
        if not self.partner_id:
            raise UserError(f"Cannot create credit note for member {member.name}. Ensure the policy has a valid Related Contact assigned.")
        account = self.env["account.account"].search([("account_type", "=", "income")], limit=1)
        if not account:
            raise UserError("No income account found. Configure an income account in Accounting > Configuration > Chart of Accounts.")
        if not member.locked_premium and not member.premium:
            _logger.warning(f"Member {member.name} has no premium to refund. Skipping credit note creation.")
            return False

        refund_amount = 0.0
        covered_days = 0
        non_covered_days = 0

        if member.state == 'deleted' and self.state == 'active' and (member.locked_premium or member.premium):
            end_date = self.end_date
            deletion_date = (member.deletion_date or fields.Datetime.now()).date()
            start_date = None
            invoice_line = member.invoice_line_ids.filtered(lambda l: l.move_id.move_type == 'out_invoice' and l.move_id.payment_state == 'paid')[:1]
            if invoice_line and invoice_line.move_id.invoice_date:
                start_date = invoice_line.move_id.invoice_date
            else:
                start_date = (member.creation_date or member.activation_date or self.active_date or fields.Datetime.now()).date()

            if not end_date or end_date <= start_date or deletion_date < start_date:
                _logger.warning(f"Invalid dates for policy {self.name} and member {member.name}. Skipping credit note.")
                return False

            covered_days = (end_date - start_date).days
            non_covered_days = (end_date - deletion_date).days
            if covered_days > 0 and non_covered_days > 0 and non_covered_days <= covered_days:
                proration_ratio = non_covered_days / covered_days
                refund_amount = (member.premium) * proration_ratio

        if refund_amount <= 0:
            _logger.info(f"No refundable amount for member {member.name}. Skipping credit note.")
            return False

        credit_note = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": self.partner_id.id,
            "invoice_line_ids": [(0, 0, {
                "name": f"{self.name} - Credit for deleted member: {member.name} ({member.band_label or member.relation_type})",
                "quantity": 1,
                "price_unit": refund_amount,
                "account_id": account.id,
                "insurance_policy_member_id": member.id,
            })],
            "insurance_policy_id": self.id,
        })
        credit_note.action_post()
        _logger.info(f"Credit note {credit_note.name} created for member {member.name} in policy {self.name} with refund amount {refund_amount}.")
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': credit_note.id,
            'target': 'current',
        }

    def action_claim(self):
        self.ensure_one()
        claim = self.env["medical.claim"].create({"underwriter_id": self.insurer_id.id, "contact_id": self.partner_id.id})
        self.claim_id = claim.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Insurance Policy"),
            "res_model": "medical.claim",
            "view_mode": "form",
            "res_id": self.claim_id.id,
        }

    # def _send_policy_renewal_reminders(self):
    #     from dateutil.relativedelta import relativedelta  # Import here to avoid circular imports
    #     today = fields.Date.today()
    #     intervals = [60, 40, 30]
    #     for days_before in intervals:
    #         target_date = today + relativedelta(days=days_before)
    #         policies = self.search([('end_date', '=', target_date), ('state', '=', 'active')])
    #         for policy in policies:
    #             if not policy.partner_id.email:
    #                 continue
    #             template = self.env.ref('innovus_brokerage.email_template_policy_renewal_reminder', raise_if_not_found=False)
    #             if template:
    #                 template.send_mail(policy.id, force_send=True)

    def action_create_cr_report(self):
        self.ensure_one()
        cr_report = self.env['insurance.policy.cr.report'].create({'policy_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'insurance.policy.cr.report',
            'view_mode': 'form',
            'res_id': cr_report.id,
            'target': 'current',
        }


    