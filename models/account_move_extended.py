from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    length = fields.Float(
        string='Length',
        default=1.0,
        help="Multiply quantity by this length to compute effective quantity."
    )

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id', 'length')
    def _compute_totals(self):
        """Compute 'price_subtotal' / 'price_total' considering length factor."""
        AccountTax = self.env['account.tax']
        for line in self:
            # TODO remove the need of cogs lines to have a price_subtotal/price_total
            if line.display_type not in ('product', 'cogs'):
                line.price_total = line.price_subtotal = False
                continue

            # Get the base line for tax computation
            base_line = line.move_id._prepare_product_base_line_for_taxes_computation(line)

            # CRITICAL FIX: Apply length factor to quantity BEFORE tax computation
            if line.length and line.length != 1.0:
                base_line['quantity'] = base_line.get('quantity', line.quantity or 0.0) * line.length

            # Compute taxes with the modified quantity
            AccountTax._add_tax_details_in_base_line(base_line, line.company_id)
            line.price_subtotal = base_line['tax_details']['raw_total_excluded_currency']
            line.price_total = base_line['tax_details']['raw_total_included_currency']

    def _prepare_base_line_for_taxes_computation(self):
        """Ensure length is applied to invoice base tax computations."""
        res = super()._prepare_base_line_for_taxes_computation()
        if not self.display_type and self.length and self.length != 1.0:
            # Apply length factor to quantity for tax computation
            res['quantity'] = res.get('quantity', self.quantity or 0.0) * self.length
        return res

    @api.onchange('length')
    def _onchange_length(self):
        """Update invoice totals when length changes."""
        # Recompute line amounts
        self._compute_totals()

        # Force recomputation of invoice totals
        if self.move_id:
            self.move_id._recompute_dynamic_lines(recompute_all_taxes=True)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _recompute_tax_lines(self, recompute_tax_base_amount=False):
        """Override to ensure tax lines are computed with length consideration."""
        # First ensure all line subtotals are computed with our custom logic
        for line in self.invoice_line_ids:
            if not line.display_type:
                line._compute_totals()  # Use our custom computation

        # Now call the original computation
        return super()._recompute_tax_lines(recompute_tax_base_amount=recompute_tax_base_amount)

    def _prepare_product_base_line_for_taxes_computation(self, line):
        """Override to ensure length is considered in base line preparation."""
        base_line = super()._prepare_product_base_line_for_taxes_computation(line)

        # Apply length factor to quantity for tax computation
        if line.length and line.length != 1.0 and not line.display_type:
            base_line['quantity'] = base_line.get('quantity', line.quantity or 0.0) * line.length

        return base_line