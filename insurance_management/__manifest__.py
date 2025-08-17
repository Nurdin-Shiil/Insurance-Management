# -*- coding: utf-8 -*-
{
    'name': 'Insurance Management',
    'version': '1.0',
    'summary': 'Handle Insurance Business Development and Policy Management.',
    'category': 'Sales',
    'author': 'Code Kenya',
    'depends': ['base', 'crm', 'account', 'base_automation', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/rate_table_views.xml',
        'views/policy_views.xml',
        'views/quick_quote_views.xml',
        'views/import_members_views.xml',
        'reports/quote_report_new.xml',  # 
        'reports/templates.xml',  # 
        'views/partner_views.xml',
        'views/crm_lead_views.xml',
        'views/menu_views.xml',
        'views/cr_report.xml',
        'data/automated_actions.xml',
        'data/insurance_policy_sequence.xml',
        'data/email_template.xml',
        'reports/report_medical_benefit.xml',
        'views/policy_masterlist.xml',
        'views/medical_benefit_views.xml',
        'views/commission_views.xml',
        'views/portal_template.xml',
        'reports/risk_note_template.xml',
        'views/lead_quote_views.xml',
        'views/quote_request_wizard_views.xml',



    ],
    'images': [
        'static/description/icon.png',
    ],
    'installable': True,
    'application': True,
}