from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError
from odoo import fields

class DocumentController(http.Controller):

    @http.route('/report/pdf/medical_benefit/<int:lead_id>', type='http', auth='user')
    def preview_risk_note(self, lead_id):
        report_name = 'insurance_management.report_medical_benefit'
        return request.redirect(f'/report/pdf/{report_name}/{lead_id}')
    

class QuoteUploadController(http.Controller):
    @http.route(['/innovus/quote/upload/<string:token>', '/innovus/quote/upload/<string:token>/submit'], auth='public', website=True)
    def quote_upload(self, token, **post):
        quote = request.env['lead.quote'].sudo().search([('access_token', '=', token)], limit=1)
        if not quote or quote.token_expiry < fields.Date.today():
            return request.render('insurance_management.quote_upload_error', {'error': 'Invalid or expired token.'})

        if request.httprequest.method == 'POST':
            try:
                quote_document = post.get('quote_document')
                if not quote_document:
                    return request.render('insurance_management.quote_upload_error', {'error': 'Please upload a PDF document.'})
                quote.write({
                    'quote_document': quote_document.read(),
                    'quote_document_filename': quote_document.filename,
                    'premium_amount': float(post.get('premium_amount', 0)),
                    'coverage_terms': post.get('coverage_terms'),
                    'submission_date': fields.Date.today(),
                })
                return request.render('insurance_management.quote_upload_success', {'lead': quote.lead_id})
            except Exception as e:
                return request.render('insurance_management.quote_upload_error', {'error': str(e)})

        return request.render('insurance_management.quote_upload_form', {
            'lead': quote.lead_id,
            'underwriter': quote.partner_id,
            'token': token,
        })