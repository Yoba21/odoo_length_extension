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

    def _get_rounded_base_and_tax_lines(self, round_from_tax_lines=True):
        """Override to ensure length factor is applied in ALL tax computations."""
        self.ensure_one()
        AccountTax = self.env['account.tax']
        is_invoice = self.is_invoice(include_receipts=True)

        if self.id or not is_invoice:
            base_amls = self.line_ids.filtered(lambda line: line.display_type == 'product')
        else:
            base_amls = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')

        # CRITICAL FIX: Apply length factor to ALL base lines for tax computation
        base_lines = []
        for line in base_amls:
            base_line = self._prepare_product_base_line_for_taxes_computation(line)
            # Ensure length is applied
            if line.length and line.length != 1.0:
                base_line['quantity'] = base_line.get('quantity', line.quantity or 0.0) * line.length
            base_lines.append(base_line)

        tax_lines = []
        if self.id:
            # The move is stored so we can add the early payment discount lines directly to reduce the
            # tax amount without touching the untaxed amount.
            epd_amls = self.line_ids.filtered(lambda line: line.display_type == 'epd')
            base_lines += [self._prepare_epd_base_line_for_taxes_computation(line) for line in epd_amls]
            cash_rounding_amls = self.line_ids \
                .filtered(lambda line: line.display_type == 'rounding' and not line.tax_repartition_line_id)
            base_lines += [self._prepare_cash_rounding_base_line_for_taxes_computation(line) for line in
                           cash_rounding_amls]
            AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
            tax_amls = self.line_ids.filtered('tax_repartition_line_id')
            tax_lines = [self._prepare_tax_line_for_taxes_computation(tax_line) for tax_line in tax_amls]
            AccountTax._round_base_lines_tax_details(base_lines, self.company_id,
                                                     tax_lines=tax_lines if round_from_tax_lines else [])
        else:
            # The move is not stored yet so the only thing we have is the invoice lines.
            base_lines += self._prepare_epd_base_lines_for_taxes_computation_from_base_lines(base_amls)
            AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, self.company_id)
        return base_lines, tax_lines

    def _prepare_product_base_line_for_taxes_computation(self, line):
        """Override to ensure length is considered in base line preparation."""
        base_line = super()._prepare_product_base_line_for_taxes_computation(line)

        # Apply length factor to quantity for tax computation
        if line.length and line.length != 1.0 and not line.display_type:
            base_line['quantity'] = base_line.get('quantity', line.quantity or 0.0) * line.length

        return base_line

    def _compute_tax_totals(self):
        """Override tax totals computation to ensure length factor is applied."""
        for move in self:
            if move.is_invoice(include_receipts=True):
                # Get base lines with length factor applied
                base_lines, _tax_lines = move._get_rounded_base_and_tax_lines()

                # CRITICAL: Ensure we use the modified base lines for tax totals
                move.tax_totals = self.env['account.tax']._get_tax_totals_summary(
                    base_lines=base_lines,
                    currency=move.currency_id,
                    company=move.company_id,
                    cash_rounding=move.invoice_cash_rounding_id,
                )
                move.tax_totals['display_in_company_currency'] = (
                        move.company_id.display_invoice_tax_company_currency
                        and move.company_currency_id != move.currency_id
                        and move.tax_totals['has_tax_groups']
                        and move.is_sale_document(include_receipts=True)
                )
            else:
                # Non-invoice moves don't support that field
                move.tax_totals = None

    @api.depends('line_ids.matched_debit_ids.debit_move_id.move_id.origin_payment_id.is_matched',
                 'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual',
                 'line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency',
                 'line_ids.matched_credit_ids.credit_move_id.move_id.origin_payment_id.is_matched',
                 'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual',
                 'line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency',
                 'line_ids.balance',
                 'line_ids.currency_id',
                 'line_ids.amount_currency',
                 'line_ids.amount_residual',
                 'line_ids.amount_residual_currency',
                 'line_ids.payment_id.state',
                 'line_ids.full_reconcile_id',
                 'state')
    def _compute_amount(self):
        """Override amount computation to ensure length factor is considered."""
        # First ensure all line amounts are computed with our custom logic
        for move in self:
            if move.is_invoice(include_receipts=True):
                # Force recomputation of line totals with length factor
                move.line_ids._compute_totals()

        # Now call the original computation which will use our updated line values
        return super()._compute_amount()

    def _recompute_dynamic_lines(self, recompute_all_taxes=True, recompute_tax_base_amount=False):
        """Override to ensure our custom computations are used."""
        # Force recomputation of line totals with length factor
        self.line_ids._compute_totals()

        # Now call the original method
        return super()._recompute_dynamic_lines(
            recompute_all_taxes=recompute_all_taxes,
            recompute_tax_base_amount=recompute_tax_base_amount
        )