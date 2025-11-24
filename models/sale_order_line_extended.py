from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    length = fields.Float(
        string='Length(Meters)',
        default=1.0,
        help="Multiply quantity by this length to compute effective quantity."
    )

    @api.depends('product_uom_qty', 'price_unit', 'discount', 'tax_id', 'length')
    def _compute_amount(self):
        """Compute line amounts considering length."""
        for line in self:
            if line.display_type:
                line.price_subtotal = 0.0
                line.price_tax = 0.0
                line.price_total = 0.0
                continue

            # Calculate effective quantity considering length
            qty = (line.product_uom_qty or 0.0) * (line.length or 1.0)
            price = (line.price_unit or 0.0) * (1 - (line.discount or 0.0) / 100)
            taxes = line.tax_id.compute_all(
                price,
                currency=line.order_id.currency_id,
                quantity=qty,
                product=line.product_id,
                partner=line.order_id.partner_id
            )
            line.update({
                'price_subtotal': taxes['total_excluded'],
                'price_tax': taxes['total_included'] - taxes['total_excluded'],
                'price_total': taxes['total_included'],
            })

    def _prepare_base_line_for_taxes_computation(self):
        """Override to include length in quantity for tax computation."""
        base_line = super()._prepare_base_line_for_taxes_computation()
        # Apply length factor to quantity
        if not self.display_type and self.length and self.length != 1.0:
            base_line['quantity'] = (base_line.get('quantity', 0.0) or self.product_uom_qty) * self.length
        return base_line

    @api.onchange('length')
    def _onchange_length(self):
        """Update order totals when length changes."""
        self._compute_amount()

        # Force recomputation of order totals
        if self.order_id:
            self.order_id._compute_amounts()

    def _prepare_invoice_line(self, **optional_values):
        """
        Ensure LENGTH is correctly transferred from Sale Order Line to Invoice Line.
        This method MUST accept **optional_values because Odoo passes kwargs.
        """
        vals = super()._prepare_invoice_line(**optional_values)

        # Copy the length to the invoice line
        vals['length'] = self.length or 1.0

        return vals


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id')
    def _compute_amounts(self):
        """Override to ensure our line amounts with length are used."""
        self.mapped('order_line')._compute_amount()

        return super()._compute_amounts()
