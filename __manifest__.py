{
    'name': 'Odoo Length Extension',
    'version': '18.0.1.0',
    'author': 'Eyob',
    'category': 'Uncategorized',
    'description': "Length Columun in Invoice, Qoutation, and Order",
    'license':'LGPL-3',
    "depends": ['sale', ],
    'data': [
        'views/sales_order_extended_view.xml',
        'views/account_move_extended.xml',
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}