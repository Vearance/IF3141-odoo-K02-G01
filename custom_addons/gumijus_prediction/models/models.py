import base64
import csv
import io
from datetime import date, datetime

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class GumijusStokHarian(models.Model):
    _name = 'gumijus.stok.harian'
    _description = 'Pemakaian dan Stok Harian'
    _order = 'tanggal desc, id_cabang, id_bahan'

    name = fields.Char(string='Nama Catatan', compute='_compute_name', store=True)
    tanggal = fields.Date(string='Tanggal', required=True, default=fields.Date.context_today)
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', required=True)
    id_bahan = fields.Many2one(
        'product.product', string='Bahan Baku', required=True,
        domain="[('categ_id.name', '=', 'Bahan Baku')]")
    saldo_awal = fields.Float(string='Saldo Awal', default=0.0)
    jml_masuk = fields.Float(string='Jumlah Masuk', default=0.0)
    jml_pakai = fields.Float(string='Jumlah Pakai', default=0.0)
    sisa_stok = fields.Float(
        string='Sisa Stok', compute='_compute_sisa_stok', store=True)
    stok_aktual = fields.Float(
        string='Stok Aktual', compute='_compute_sisa_stok', store=True)
    satuan = fields.Many2one(
        related='id_bahan.uom_id', string='Satuan', readonly=True)
    status_closing = fields.Selection([
        ('draft', 'Belum Closing'),
        ('closing', 'Closing'),
    ], string='Status Closing', default='draft')
    catatan = fields.Char(string='Catatan')

    @api.depends('tanggal', 'id_cabang', 'id_bahan')
    def _compute_name(self):
        for rec in self:
            rec.name = 'Stok Harian - %s - %s' % (
                rec.id_bahan.name or 'Bahan Baku',
                rec.tanggal.strftime('%d/%m/%Y') if rec.tanggal else '',
            )

    @api.depends('saldo_awal', 'jml_masuk', 'jml_pakai')
    def _compute_sisa_stok(self):
        for rec in self:
            rec.sisa_stok = rec.saldo_awal + rec.jml_masuk - rec.jml_pakai
            rec.stok_aktual = rec.sisa_stok

    @api.constrains('saldo_awal', 'jml_masuk', 'jml_pakai', 'sisa_stok')
    def _check_kuantitas_non_negatif(self):
        for rec in self:
            if min(rec.saldo_awal, rec.jml_masuk, rec.jml_pakai, rec.sisa_stok) < 0:
                raise ValidationError(
                    'Nilai kuantitas (saldo awal, jumlah masuk, jumlah pakai, '
                    'dan sisa stok) tidak boleh negatif.')

    def action_closing(self):
        for rec in self:
            rec.status_closing = 'closing'


class GumijusRekapStok(models.Model):
    _name = 'gumijus.rekap.stok'
    _description = 'Rekapitulasi Stok per Cabang'
    _auto = False
    _order = 'id_cabang, id_bahan'

    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', readonly=True)
    id_bahan = fields.Many2one('product.product', string='Bahan Baku', readonly=True)
    satuan = fields.Many2one(related='id_bahan.uom_id', string='Satuan', readonly=True)
    jml_masuk = fields.Float(string='Jumlah Masuk', readonly=True)
    jml_pakai = fields.Float(string='Jumlah Pakai', readonly=True)
    sisa_stok = fields.Float(string='Sisa Stok', readonly=True)

    def action_export(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/gumijus/export/rekap?format=csv',
            'target': 'self',
        }


class GumijusImportLog(models.Model):
    _name = 'gumijus.import.log'
    _description = 'Log Impor Berkas Data'
    _order = 'tanggal_impor desc, id desc'

    REQUIRED_COLUMNS = {
        'penjualan': ['tanggal', 'id_cabang', 'menu', 'jml_penjualan'],
        'stok_bom': ['id_bahan', 'kuantitas_per_porsi', 'stok'],
        'cuaca': ['tanggal', 'id_cabang', 'suhu', 'curah_hujan'],
    }

    name = fields.Char(string='Nama Impor', required=True, default='Impor Berkas Data')
    jenis_berkas = fields.Selection([
        ('penjualan', 'Data Penjualan'),
        ('stok_bom', 'Data Stok dan BoM'),
        ('cuaca', 'Data Cuaca'),
    ], string='Jenis Berkas', required=True, default='penjualan')
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang')
    file_name = fields.Char(string='Nama Berkas')
    file_data = fields.Binary(string='Berkas', attachment=True)
    tanggal_impor = fields.Datetime(string='Tanggal Impor', default=fields.Datetime.now)
    status = fields.Selection([
        ('baru', 'Baru'),
        ('valid', 'Valid'),
        ('ditolak', 'Ditolak'),
    ], string='Status', default='baru')
    jumlah_baris = fields.Integer(string='Jumlah Baris')
    pesan_galat = fields.Text(string='Pesan Galat')

    def _baca_csv(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError('Unggah berkas terlebih dahulu sebelum melakukan validasi.')
        try:
            isi = base64.b64decode(self.file_data).decode('utf-8-sig')
        except Exception as exc:
            raise UserError('Berkas tidak dapat dibaca sebagai CSV: %s' % exc)
        baris = list(csv.reader(io.StringIO(isi)))
        if not baris:
            raise UserError('Berkas kosong atau tidak memiliki baris header.')
        header = [h.strip().lower() for h in baris[0]]
        return header, baris[1:]

    def action_validasi(self):
        for rec in self:
            rec.pesan_galat = False
            rec.jumlah_baris = 0
            header, baris = rec._baca_csv()
            wajib = rec.REQUIRED_COLUMNS[rec.jenis_berkas]
            hilang = [kolom for kolom in wajib if kolom not in header]
            if hilang:
                rec.status = 'ditolak'
                rec.pesan_galat = (
                    "Kolom %s tidak ditemukan pada baris 1. "
                    "Kolom wajib: %s."
                    % (', '.join("'%s'" % k for k in hilang),
                       ', '.join("'%s'" % k for k in wajib)))
                continue

            galat = []
            jumlah = 0
            for nomor, row in enumerate(baris, start=2):
                if not any(cell.strip() for cell in row):
                    continue
                jumlah += 1
                data = dict(zip(header, row))
                for kolom in wajib:
                    nilai = (data.get(kolom) or '').strip()
                    if not nilai:
                        galat.append(
                            "Kolom '%s' pada baris %d kosong." % (kolom, nomor))
                        continue
                    try:
                        angka = float(nilai)
                        if angka < 0:
                            galat.append(
                                "Kolom '%s' pada baris %d bernilai negatif (%.2f)."
                                % (kolom, nomor, angka))
                    except ValueError:
                        if kolom not in ('tanggal', 'id_cabang', 'menu', 'id_bahan'):
                            galat.append(
                                "Kolom '%s' pada baris %d bukan angka yang valid."
                                % (kolom, nomor))
            rec.jumlah_baris = jumlah
            if galat:
                rec.status = 'ditolak'
                rec.pesan_galat = '\n'.join(galat[:12])
            else:
                rec.status = 'valid'
                rec.pesan_galat = False

    def action_impor(self):
        for rec in self:
            rec.action_validasi()
            if rec.status != 'valid':
                continue
            header, baris = rec._baca_csv()
            if rec.jenis_berkas == 'penjualan':
                for row in baris:
                    if not any(cell.strip() for cell in row):
                        continue
                    data = dict(zip(header, row))
                    cabang = self._cari_cabang(data.get('id_cabang', ''))
                    menu = self.env['product.product'].search(
                        [('name', '=', data.get('menu', '').strip())], limit=1)
                    tanggal = self._parse_tanggal(data.get('tanggal'))
                    if cabang and tanggal:
                        self.env['gumijus.dataset'].create({
                            'tanggal': tanggal,
                            'id_cabang': cabang.id,
                            'id_bahan': menu.id if menu else False,
                            'est_porsi_terjual': float(data.get('jml_penjualan') or 0),
                            'sumber': 'Penjualan',
                        })
            elif rec.jenis_berkas == 'cuaca':
                for row in baris:
                    if not any(cell.strip() for cell in row):
                        continue
                    data = dict(zip(header, row))
                    cabang = self._cari_cabang(data.get('id_cabang', ''))
                    tanggal = self._parse_tanggal(data.get('tanggal'))
                    if not (cabang and tanggal):
                        continue
                    dataset = self.env['gumijus.dataset'].search([
                        ('tanggal', '=', tanggal),
                        ('id_cabang', '=', cabang.id),
                    ], limit=1)
                    nilai = {
                        'suhu': float(data.get('suhu') or 0),
                        'curah_hujan': float(data.get('curah_hujan') or 0),
                        'sumber': 'Cuaca',
                    }
                    if dataset:
                        dataset.write(nilai)
                    else:
                        nilai.update({
                            'tanggal': tanggal,
                            'id_cabang': cabang.id,
                        })
                        self.env['gumijus.dataset'].create(nilai)

    def _cari_cabang(self, nilai):
        nilai = (nilai or '').strip()
        if not nilai:
            return False
        return self.env['stock.warehouse'].search([
            '|', ('code', '=', nilai), ('name', 'ilike', nilai),
        ], limit=1)

    def _parse_tanggal(self, nilai):
        if not nilai:
            return False
        for pola in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(nilai.strip(), pola).date()
            except ValueError:
                continue
        return False


class GumijusDataset(models.Model):
    _name = 'gumijus.dataset'
    _description = 'Dataset Penjualan dan Cuaca'
    _order = 'tanggal desc, id_cabang, id_bahan'

    tanggal = fields.Date(string='Tanggal', required=True)
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', required=True)
    id_bahan = fields.Many2one(
        'product.product', string='Menu/Bahan',
        domain="[('categ_id.name', 'in', ['Bahan Baku', 'Menu Jus'])]")
    est_porsi_terjual = fields.Float(string='Estimasi Porsi Terjual')
    jumlah_terjual = fields.Integer(
        string='Jumlah Terjual', compute='_compute_jumlah_terjual', store=True)
    suhu = fields.Float(string='Suhu (°C)')
    curah_hujan = fields.Float(string='Curah Hujan (mm)')
    sumber = fields.Char(string='Sumber Data')
    status_validasi = fields.Selection([
        ('valid', 'Valid'),
        ('ditolak', 'Ditolak'),
    ], string='Status Validasi', default='valid')

    @api.depends('est_porsi_terjual')
    def _compute_jumlah_terjual(self):
        for rec in self:
            rec.jumlah_terjual = int(round(rec.est_porsi_terjual or 0))


class GumijusPrediksi(models.Model):
    _name = 'gumijus.prediksi'
    _description = 'Proses Prediksi Kebutuhan Bahan Baku'
    _order = 'tanggal_jalan desc, id desc'

    name = fields.Char(string='Nama Proses', required=True,
                       default='Prediksi Kebutuhan Bahan Baku')
    periode_mulai = fields.Date(string='Periode Mulai', required=True)
    periode_selesai = fields.Date(string='Periode Selesai', required=True)
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', required=True)
    versi_model = fields.Char(string='Versi Model', default='v1.4.0')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('proses', 'Diproses'),
        ('selesai', 'Selesai'),
    ], string='Status', default='draft')
    tanggal_jalan = fields.Datetime(string='Tanggal Dijalankan')
    tanggal = fields.Date(
        string='Tanggal', compute='_compute_tanggal', store=True)
    catatan = fields.Text(string='Catatan')
    rekomendasi_ids = fields.One2many(
        'gumijus.rekomendasi', 'prediksi_id', string='Rekomendasi')

    @api.depends('tanggal_jalan')
    def _compute_tanggal(self):
        for rec in self:
            rec.tanggal = rec.tanggal_jalan.date() if rec.tanggal_jalan else False

    def action_jalankan(self):
        for rec in self:
            if rec.periode_selesai < rec.periode_mulai:
                raise UserError('Periode selesai tidak boleh lebih awal dari periode mulai.')
            rec.write({
                'status': 'selesai',
                'tanggal_jalan': fields.Datetime.now(),
            })

    def action_lihat_rekomendasi(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Rekomendasi Pengadaan',
            'res_model': 'gumijus.rekomendasi',
            'view_mode': 'list,form',
            'domain': [('prediksi_id', '=', self.id)],
            'context': {'default_prediksi_id': self.id},
        }


class GumijusRekomendasi(models.Model):
    _name = 'gumijus.rekomendasi'
    _description = 'Rekomendasi Pengadaan Bahan Baku'
    _order = 'periode desc, id_cabang, id_bahan'

    periode = fields.Date(string='Periode', required=True)
    tanggal = fields.Date(
        string='Tanggal', related='periode', store=True)
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', required=True)
    id_bahan = fields.Many2one('product.product', string='Bahan Baku', required=True,
                               domain="[('categ_id.name', '=', 'Bahan Baku')]")
    prediksi_id = fields.Many2one('gumijus.prediksi', string='Proses Prediksi')
    est_porsi_terjual = fields.Float(string='Estimasi Porsi Terjual')
    estimasi_kebutuhan = fields.Float(string='Estimasi Kebutuhan')
    kebutuhan_kotor = fields.Float(
        string='Kebutuhan Kotor', related='estimasi_kebutuhan', store=True)
    stok_saat_ini = fields.Float(string='Stok Saat Ini')
    rek_pengadaan = fields.Float(
        string='Rekomendasi Pengadaan', compute='_compute_rek_pengadaan', store=True)
    nama_bahan = fields.Char(related='id_bahan.name', string='Bahan Baku')
    satuan = fields.Many2one(related='id_bahan.uom_id', string='Satuan', readonly=True)
    status = fields.Selection([
        ('kurang', 'Perlu Pengadaan'),
        ('cukup', 'Stok Cukup'),
    ], string='Status Pasokan', compute='_compute_status', store=True)

    @api.depends('estimasi_kebutuhan', 'stok_saat_ini')
    def _compute_rek_pengadaan(self):
        for rec in self:
            rec.rek_pengadaan = max(0.0, rec.estimasi_kebutuhan - rec.stok_saat_ini)

    @api.depends('rek_pengadaan')
    def _compute_status(self):
        for rec in self:
            rec.status = 'kurang' if rec.rek_pengadaan > 0 else 'cukup'

    @api.constrains('estimasi_kebutuhan', 'stok_saat_ini', 'rek_pengadaan')
    def _check_nilai_non_negatif(self):
        for rec in self:
            if min(rec.estimasi_kebutuhan, rec.stok_saat_ini, rec.rek_pengadaan) < 0:
                raise ValidationError('Estimasi kebutuhan, stok, dan rekomendasi pengadaan tidak boleh negatif.')

    def action_export(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/gumijus/export/rekomendasi?format=csv',
            'target': 'self',
        }

    @api.model
    def get_dashboard_data(self, cabang_id=False, periode=False, bahan_id=False):
        warehouses = self.env['stock.warehouse'].search(
            [('code', 'in', ['TBI', 'SKJ', 'BBT', 'GKL'])], order='id')
        branches = warehouses
        if cabang_id:
            branches = branches.filtered(lambda w: w.id == int(cabang_id))

        domain = []
        if branches:
            domain.append(('id_cabang', 'in', branches.ids))
        if bahan_id:
            domain.append(('id_bahan', '=', int(bahan_id)))
        if periode:
            try:
                tahun, bulan = [int(x) for x in str(periode).split('-')]
                awal = date(tahun, bulan, 1)
                akhir = date(tahun + (bulan // 12), (bulan % 12) + 1, 1)
                domain += [('periode', '>=', awal), ('periode', '<', akhir)]
            except Exception:
                pass

        rekomendasi = self.search(domain, order='periode, id_cabang, id_bahan')
        semua_rekomendasi = self.search(
            [('id_cabang', 'in', warehouses.ids)] +
            ([('id_bahan', '=', int(bahan_id))] if bahan_id else []),
            order='periode')

        label_periode = []
        for rec in semua_rekomendasi:
            kunci = rec.periode.strftime('%Y-%m')
            if kunci not in label_periode:
                label_periode.append(kunci)
        label_periode = sorted(label_periode)[-4:]
        if not label_periode:
            label_periode = ['2026-08', '2026-09', '2026-10', '2026-11']

        warna = ['#2e7d32', '#ef6c00', '#1565c0', '#6a1b9a']
        trend = []
        for idx, cabang in enumerate(branches):
            nilai = []
            for kunci in label_periode:
                total = sum(
                    rec.estimasi_kebutuhan
                    for rec in semua_rekomendasi
                    if rec.id_cabang == cabang and rec.periode.strftime('%Y-%m') == kunci
                )
                nilai.append(round(total, 2))
            trend.append({
                'cabang': cabang.name,
                'color': warna[idx % len(warna)],
                'values': nilai,
            })

        bahan_domain = [('categ_id.name', '=', 'Bahan Baku')]
        if bahan_id:
            bahan_domain.append(('id', '=', int(bahan_id)))
        bahan = self.env['product.product'].search(bahan_domain, order='name')
        stok = {}
        for produk in bahan:
            stok[produk.id] = {
                'bahan': produk.name,
                'satuan': produk.uom_id.name or '',
                'stok': 0.0,
            }
        for cabang in branches:
            quants = self.env['stock.quant'].search([
                ('location_id', 'child_of', cabang.lot_stock_id.id),
                ('product_id.categ_id.name', '=', 'Bahan Baku'),
            ])
            for quant in quants:
                if quant.product_id.id in stok:
                    stok[quant.product_id.id]['stok'] += quant.quantity
        stok_ringkas = []
        for nilai in stok.values():
            nilai['stok'] = round(nilai['stok'], 2)
            nilai['status'] = 'Aman' if nilai['stok'] > 0 else 'Kritis'
            stok_ringkas.append(nilai)
        stok_ringkas.sort(key=lambda x: x['bahan'])

        cuaca = []
        for cabang in branches:
            data = self.env['gumijus.dataset'].search([
                ('id_cabang', '=', cabang.id),
                ('sumber', '=', 'Cuaca'),
            ], order='tanggal desc', limit=1)
            if data:
                if data.curah_hujan <= 0:
                    kondisi = 'Cerah'
                elif data.curah_hujan < 5:
                    kondisi = 'Berawan'
                else:
                    kondisi = 'Hujan'
                cuaca.append({
                    'cabang': cabang.name,
                    'tanggal': data.tanggal.strftime('%d/%m/%Y'),
                    'kondisi': kondisi,
                    'suhu': data.suhu,
                    'curah_hujan': data.curah_hujan,
                })

        evaluasi = self.env['gumijus.evaluasi'].search(
            [('id_cabang', 'in', warehouses.ids)], order='nilai_wape desc')
        perlu_retrain = any(rec.nilai_wape > rec.ambang_batas for rec in evaluasi)
        evaluasi_tertinggi = evaluasi[:1]
        pelatihan = self.env['gumijus.pelatihan'].search(
            [('status', '=', 'selesai')], order='tanggal desc', limit=1)

        nama_bulan_singkat = [
            'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
            'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des',
        ]
        procurement = []
        for rec in rekomendasi[:20]:
            procurement.append({
                'periode': '%s %d' % (nama_bulan_singkat[rec.periode.month - 1], rec.periode.year),
                'cabang': rec.id_cabang.name,
                'bahan': rec.id_bahan.name,
                'estimasi': round(rec.estimasi_kebutuhan, 2),
                'rekomendasi': round(rec.rek_pengadaan, 2),
                'satuan': rec.satuan.name or '',
                'status': 'Perlu Pengadaan' if rec.status == 'kurang' else 'Stok Cukup',
                'status_code': rec.status,
            })

        periode_options = []
        for kunci in sorted({rec.periode.strftime('%Y-%m') for rec in semua_rekomendasi}, reverse=True):
            tahun, bulan = [int(x) for x in kunci.split('-')]
            nama_bulan = [
                'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
            ][bulan - 1]
            periode_options.append({
                'value': kunci,
                'label': '%s %d' % (nama_bulan, tahun),
            })
        if not periode_options:
            periode_options = [{'value': '2026-11', 'label': 'November 2026'}]

        return {
            'cabang_options': [{'id': w.id, 'name': w.name} for w in warehouses],
            'bahan_options': [{'id': b.id, 'name': b.name} for b in bahan],
            'periode_options': periode_options,
            'trend_labels': [
                ['Agustus', 'September', 'Oktober', 'November'][i]
                if len(label_periode) == 4 else item
                for i, item in enumerate(label_periode)
            ],
            'trend_series': trend,
            'stock_summary': stok_ringkas,
            'weather': cuaca,
            'procurement': procurement,
            'model_status': 'Perlu Pelatihan Ulang' if perlu_retrain else 'OK',
            'model_note': (
                'WAPE tertinggi %.1f%% pada %s (ambang batas 25%%).'
                % (evaluasi_tertinggi.nilai_wape, evaluasi_tertinggi.id_cabang.name)
                if evaluasi_tertinggi else 'Belum ada data evaluasi.'
            ),
            'model_version': pelatihan.versi_model if pelatihan else 'v1.4.0',
        }


class GumijusEvaluasi(models.Model):
    _name = 'gumijus.evaluasi'
    _description = 'Evaluasi Akurasi Model Prediksi'
    _order = 'periode_mulai desc, id_cabang'

    name = fields.Char(string='Nama Evaluasi', required=True,
                       default='Evaluasi Akurasi Model')
    periode_mulai = fields.Date(string='Periode Mulai', required=True)
    periode_selesai = fields.Date(string='Periode Selesai', required=True)
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', required=True)
    total_aktual = fields.Float(string='Total Aktual')
    total_prediksi = fields.Float(string='Total Prediksi')
    variance = fields.Float(
        string='Variance (Prediksi - Aktual)',
        compute='_compute_variance', store=True)
    deviasi_total = fields.Float(
        string='Deviasi Total', related='variance', store=True)
    periode = fields.Char(
        string='Periode', compute='_compute_periode', store=True)
    nilai_wape = fields.Float(string='Nilai WAPE (%)')
    ambang_batas = fields.Float(string='Ambang Batas (%)', default=25.0)
    perlu_retrain = fields.Boolean(
        string='Perlu Retrain', compute='_compute_status_model', store=True)
    status_model = fields.Selection([
        ('ok', 'OK'),
        ('retrain', 'Perlu Pelatihan Ulang'),
    ], string='Status Model', compute='_compute_status_model', store=True)
    catatan = fields.Text(string='Catatan')

    @api.depends('total_aktual', 'total_prediksi')
    def _compute_variance(self):
        for rec in self:
            rec.variance = rec.total_prediksi - rec.total_aktual

    @api.depends('periode_mulai', 'periode_selesai')
    def _compute_periode(self):
        for rec in self:
            if rec.periode_mulai and rec.periode_selesai:
                rec.periode = '%s s.d. %s' % (
                    rec.periode_mulai.strftime('%d/%m/%Y'),
                    rec.periode_selesai.strftime('%d/%m/%Y'),
                )
            else:
                rec.periode = False

    @api.depends('nilai_wape', 'ambang_batas')
    def _compute_status_model(self):
        for rec in self:
            rec.perlu_retrain = rec.nilai_wape > rec.ambang_batas
            rec.status_model = 'retrain' if rec.perlu_retrain else 'ok'


class GumijusPelatihan(models.Model):
    _name = 'gumijus.pelatihan'
    _description = 'Pelatihan Ulang Model Prediksi'
    _order = 'tanggal desc, id desc'

    name = fields.Char(string='Nama Pelatihan', required=True,
                       default='Pelatihan Ulang Model')
    tanggal = fields.Datetime(string='Tanggal Pelatihan', default=fields.Datetime.now)
    periode_data = fields.Char(string='Periode Data', default='Agustus - Oktober 2026')
    versi_model = fields.Char(string='Versi Model', default='v1.4.0')
    split_train = fields.Integer(string='Proporsi Data Latih (%)', default=80)
    split_test = fields.Integer(string='Proporsi Data Uji (%)', default=20)
    total_data = fields.Integer(string='Total Baris Data', default=0)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('selesai', 'Selesai'),
    ], string='Status', default='draft')
    line_ids = fields.One2many(
        'gumijus.pelatihan.line', 'pelatihan_id', string='WAPE per Cabang')

    @api.constrains('split_train', 'split_test')
    def _check_split(self):
        for rec in self:
            if rec.split_train < 0 or rec.split_test < 0:
                raise ValidationError('Proporsi data latih dan data uji tidak boleh negatif.')
            if rec.split_train + rec.split_test != 100:
                raise ValidationError('Total proporsi data latih dan data uji harus 100%.')

    def action_latih(self):
        for rec in self:
            rec.status = 'selesai'
            rec.tanggal = fields.Datetime.now()
            rec.line_ids.unlink()
            evaluasi = self.env['gumijus.evaluasi'].search([
                ('periode_mulai', '>=', date(2026, 8, 1)),
                ('periode_selesai', '<=', date(2026, 10, 31)),
            ])
            for data in evaluasi:
                self.env['gumijus.pelatihan.line'].create({
                    'pelatihan_id': rec.id,
                    'id_cabang': data.id_cabang.id,
                    'nilai_wape': data.nilai_wape,
                })

    def action_simpan_versi(self):
        for rec in self:
            if not rec.versi_model:
                raise UserError('Versi model wajib diisi sebelum disimpan.')
            rec.status = 'selesai'
        return True


class GumijusPelatihanLine(models.Model):
    _name = 'gumijus.pelatihan.line'
    _description = 'WAPE per Cabang pada Pelatihan Model'
    _order = 'id_cabang'

    pelatihan_id = fields.Many2one(
        'gumijus.pelatihan', string='Pelatihan', required=True, ondelete='cascade')
    id_cabang = fields.Many2one('stock.warehouse', string='Cabang', required=True)
    nilai_wape = fields.Float(string='Nilai WAPE (%)')
    ambang_batas = fields.Float(string='Ambang Batas (%)', default=25.0)
    status = fields.Selection([
        ('ok', 'OK'),
        ('retrain', 'Perlu Pelatihan Ulang'),
    ], string='Status', compute='_compute_status', store=True)

    @api.depends('nilai_wape', 'ambang_batas')
    def _compute_status(self):
        for rec in self:
            rec.status = 'retrain' if rec.nilai_wape > rec.ambang_batas else 'ok'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    masa_simpan_hari = fields.Integer(string='Masa Simpan (hari)')
    catatan_penyimpanan = fields.Text(string='Catatan Penyimpanan')
    batas_harga = fields.Float(string='Batas Harga', default=0.0)

    @api.constrains('standard_price', 'list_price', 'batas_harga')
    def _check_harga_non_negatif(self):
        for rec in self:
            if min(rec.standard_price, rec.list_price, rec.batas_harga) < 0:
                raise ValidationError(
                    'Harga pokok, harga jual, dan batas harga tidak boleh negatif.')


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    @api.constrains('product_qty')
    def _check_kuantitas_per_porsi(self):
        for rec in self:
            if rec.product_qty < 0:
                raise ValidationError('Kuantitas per porsi tidak boleh negatif.')


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    @api.constrains('product_qty')
    def _check_kuantitas_bahan(self):
        for rec in self:
            if rec.product_qty < 0:
                raise ValidationError('Kuantitas bahan pada BoM tidak boleh negatif.')


class ResUsers(models.Model):
    _inherit = 'res.users'

    gumijus_cabang_id = fields.Many2one(
        'stock.warehouse', string='Cabang Gumijus',
        help='Cabang yang boleh diakses oleh Staf Cabang.')
