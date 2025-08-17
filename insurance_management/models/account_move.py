from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    insurance_policy_id = fields.Many2one('insurance.policy', string='Related Policy', readonly=True)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    insurance_policy_member_id = fields.Many2one('insurance.policy.member', string='Policy Member', readonly=True)



class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _reconcile_payments(self, to_process, edit_mode=False):
        res = super()._reconcile_payments(to_process, edit_mode=edit_mode)

        for vals in to_process:
            lines = vals.get('to_reconcile')
            if not lines:
                continue

            for move in lines.mapped('move_id'):
                if (
                    move.move_type == 'out_invoice'
                    and move.insurance_policy_id
                    and move.insurance_policy_id.payment_type == 'broker'
                ):
                    policy = move.insurance_policy_id
                    commission_plan = policy.commission_plan_id
                    if commission_plan:
                        commission_amount = move.amount_total * commission_plan.commission_rate
                        self.env['insurance.commission'].create({
                            'commission_plan_id': commission_plan.id,
                            'policy_id': policy.id,
                            'invoice_id': move.id,
                            'commission_date': fields.Date.today(),
                            'commission_amount': commission_amount,
                        })
                        _logger.info(
                            f"Commission created for invoice {move.name} "
                            f"on policy {policy.name}: {commission_amount}."
                        )
                    move.insurance_policy_id._sync_member_states()
                    self.env.cr.commit()
                    _logger.info(
                        f"Invoice {move.name} reconciled and triggered sync "
                        f"for policy {move.insurance_policy_id.name}."
                    )

        return res