from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    length = fields.Float(string="Length(Meters)")

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to copy length from sale order line"""
        moves = super().create(vals_list)

        # Post-process: ensure length is set from sale line
        for move in moves:
            if move.sale_line_id and move.sale_line_id.length and not move.length:
                move.length = move.sale_line_id.length
                _logger.info(f"Move {move.id}: Set length={move.length} from sale line {move.sale_line_id.id}")

        return moves

    @api.model
    def _get_underlying_valued_sale_lines(self, move):
        """Helper to get sale lines for a move"""
        return move.sale_line_id

    def _action_confirm(self, merge=True, merge_into=False):
        """Override confirm to ensure length is maintained"""
        # Log before confirmation
        for move in self:
            if move.sale_line_id and move.sale_line_id.length:
                _logger.info(
                    f"Move {move.id}: Confirming with sale_line.length={move.sale_line_id.length}, current move.length={move.length}")

        result = super()._action_confirm(merge=merge, merge_into=merge_into)

        # Ensure length is set after confirmation
        for move in self:
            if move.sale_line_id and move.sale_line_id.length and not move.length:
                move.length = move.sale_line_id.length
                _logger.info(f"Move {move.id}: Set length after confirmation")

        return result

    def write(self, vals):
        res = super().write(vals)

        # If length updated on the move → propagate to move lines
        if 'length' in vals:
            for move in self:
                if move.move_line_ids:
                    move.move_line_ids.write({'length': vals['length']})
        return res


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _prepare_move_vals(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        move_vals = super()._prepare_move_vals(product_id, product_qty, product_uom, location_id, name, origin,
                                               company_id, values)

        # Copy length from sale line to stock move
        if values.get('length'):
            move_vals['length'] = values['length']

        return move_vals


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    length = fields.Float(string="Length (Meters)",
                          related='move_id.length',
                          store=True,
                          default=1.0)

    # @api.onchange('move_id')
    # def _onchange_move_id(self):
    #     for line in self:
    #         if line.move_id:
    #             line.length = line.move_id.length

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if line.move_id and line.move_id.length and not line.length:
                line.length = line.move_id.length
        return lines
