# -*- coding: utf-8 -*-
{
    'name': "Tpstudio Report System",
    'version':'19.0.1.0.0',
    'summary': """
   Odoo document report design, integrated printing PDF
       """,
    'description': """
    Odoo document report design, integrated printing PDF
    """,
    'support':'email:suport@foxmail.com',
    'author': 'tpstudio',
    'website': 'https://tpstudio.taobao.com',
    'category': 'tools/print',
    'depends': ['base','web','sale'],
    "external_dependencies": {"python": ["requests", "reportbro-lib","html2text"]},
	'sequence': 800,

    'data': [
        'security/ir.model.access.csv',
        'views/templates.xml',
		'views/report_font.xml',
    ],
   
    'application': True,
    'installable': True,
    'images':[
        'static/description/main_screenshot.png',
        'static/description/icon.png',
    ],
    'assets': {
        'web.assets_backend': [
			'tpstudio_report_system/static/src/font_preview_widget/*',
			'tpstudio_report_system/static/src/PdfPrint/*',
			'tpstudio_report_system/static/src/tpstudio_r_action_report.js',
			'tpstudio_report_system/static/src/uploadfile/*',
        ],
    },
    'license': 'LGPL-3',
	'installable': True,
    'auto_install': False,
    'application': True,
}
