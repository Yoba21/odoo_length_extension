{
    'name': 'Odoo Length Extension',
    'version': '18.0.1.0',
    'author': 'Eyob',
    'category': 'Uncategorized', 'summary': 'Adds Length field to Sale Order Lines and Invoice Lines',
    'description': """
        Adds a Length column to:
            - Sales Order lines
            - Quotation lines
            - Invoice lines
                            """,
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'account',
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
