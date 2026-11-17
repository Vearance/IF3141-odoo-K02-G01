import csv
import io

import xlsxwriter
from odoo import http
from odoo.http import request


class GumijusExportController(http.Controller):

    def _csv_response(self, filename, header, rows):
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(header)
        writer.writerows(rows)
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )

    def _xlsx_response(self, filename, header, rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Data')
        for col, title in enumerate(header):
            sheet.write(0, col, title)
        for row_idx, row in enumerate(rows, start=1):
            for col_idx, value in enumerate(row):
                sheet.write(row_idx, col_idx, value)
        workbook.close()
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )

    @http.route('/gumijus/export/rekap', type='http', auth='user', methods=['GET'])
    def export_rekap(self, format='csv', **kwargs):
        records = request.env['gumijus.rekap.stok'].search([])
        header = ['Cabang', 'Bahan Baku', 'Jumlah Masuk', 'Jumlah Pakai', 'Sisa Stok', 'Satuan']
        rows = [[
            rec.id_cabang.name or '',
            rec.id_bahan.name or '',
            rec.jml_masuk,
            rec.jml_pakai,
            rec.sisa_stok,
            rec.satuan.name or '',
        ] for rec in records]
        if format == 'xlsx':
            return self._xlsx_response('rekap_stok_gumijus.xlsx', header, rows)
        return self._csv_response('rekap_stok_gumijus.csv', header, rows)

    @http.route('/gumijus/export/rekomendasi', type='http', auth='user', methods=['GET'])
    def export_rekomendasi(self, format='csv', **kwargs):
        records = request.env['gumijus.rekomendasi'].search([])
        header = ['Periode', 'Cabang', 'Bahan Baku', 'Estimasi Kebutuhan',
                  'Stok Saat Ini', 'Rekomendasi Pengadaan', 'Satuan', 'Status']
        rows = [[
            rec.periode.strftime('%Y-%m-%d') if rec.periode else '',
            rec.id_cabang.name or '',
            rec.id_bahan.name or '',
            rec.estimasi_kebutuhan,
            rec.stok_saat_ini,
            rec.rek_pengadaan,
            rec.satuan.name or '',
            dict(rec._fields['status'].selection).get(rec.status, rec.status),
        ] for rec in records]
        if format == 'xlsx':
            return self._xlsx_response('rekomendasi_pengadaan_gumijus.xlsx', header, rows)
        return self._csv_response('rekomendasi_pengadaan_gumijus.csv', header, rows)
