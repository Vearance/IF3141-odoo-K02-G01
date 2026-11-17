from datetime import date

from odoo import api, models


class GumijusServiceMasterDanStok(models.AbstractModel):
    _name = 'gumijus.service.master.stok'
    _description = 'Layanan Master dan Stok'

    @api.model
    def kelola_bahan_baku(self, vals):
        return self.env['product.template'].create(vals)

    @api.model
    def kelola_bom(self, vals):
        return self.env['mrp.bom'].create(vals)

    @api.model
    def catat_mutasi_stok(self, vals):
        return self.env['gumijus.stok.harian'].create(vals)

    @api.model
    def perbarui_stok_aktual(self, stok_id):
        stok = self.env['gumijus.stok.harian'].browse(stok_id)
        stok.status_closing = 'closing'
        return stok.stok_aktual


class GumijusServiceAgregasiData(models.AbstractModel):
    _name = 'gumijus.service.agregasi.data'
    _description = 'Layanan Agregasi Data'

    @api.model
    def validasi_berkas(self, import_log_id):
        log = self.env['gumijus.import.log'].browse(import_log_id)
        log.action_validasi()
        return {
            'status': log.status,
            'jumlah_baris': log.jumlah_baris,
            'pesan_galat': log.pesan_galat,
        }

    @api.model
    def bersihkan_data(self, dataset_ids=None):
        domain = [('id', 'in', dataset_ids)] if dataset_ids else []
        rows = self.env['gumijus.dataset'].search(domain)
        for row in rows:
            if row.est_porsi_terjual < 0:
                row.est_porsi_terjual = 0
            if row.suhu < -50 or row.suhu > 60:
                row.suhu = 0
            if row.curah_hujan < 0:
                row.curah_hujan = 0
        return len(rows)

    @api.model
    def gabungkan_penjualan_dan_cuaca(self, cabang_id=False, tanggal_mulai=False, tanggal_selesai=False):
        domain = [('sumber', 'in', ['Penjualan', 'Cuaca'])]
        if cabang_id:
            domain.append(('id_cabang', '=', cabang_id))
        if tanggal_mulai:
            domain.append(('tanggal', '>=', tanggal_mulai))
        if tanggal_selesai:
            domain.append(('tanggal', '<=', tanggal_selesai))
        rows = self.env['gumijus.dataset'].search(domain, order='tanggal, id_cabang')
        hasil = {}
        for row in rows:
            key = (row.tanggal, row.id_cabang.id)
            data = hasil.setdefault(key, {
                'tanggal': row.tanggal,
                'id_cabang': row.id_cabang.id,
                'cabang': row.id_cabang.name,
                'jumlah_terjual': 0,
                'suhu': row.suhu,
                'curah_hujan': row.curah_hujan,
            })
            if row.sumber == 'Penjualan':
                data['jumlah_terjual'] += row.jumlah_terjual
            else:
                data['suhu'] = row.suhu
                data['curah_hujan'] = row.curah_hujan
        return list(hasil.values())


class GumijusServicePrediksi(models.AbstractModel):
    _name = 'gumijus.service.prediksi'
    _description = 'Layanan Prediksi'

    @api.model
    def prediksi_penjualan(self, cabang_id=False, periode=False):
        domain = []
        if cabang_id:
            domain.append(('id_cabang', '=', cabang_id))
        if periode:
            try:
                tahun, bulan = [int(x) for x in str(periode).split('-')]
                awal = date(tahun, bulan, 1)
                akhir = date(tahun + (bulan // 12), (bulan % 12) + 1, 1)
                domain += [('tanggal', '>=', awal), ('tanggal', '<', akhir)]
            except Exception:
                pass
        rows = self.env['gumijus.dataset'].search(domain)
        per_menu = {}
        for row in rows:
            if not row.id_bahan:
                continue
            per_menu.setdefault(row.id_bahan.id, []).append(row.est_porsi_terjual)
        return [
            {
                'id_menu': menu_id,
                'estimasi_porsi': sum(nilai) / len(nilai),
            }
            for menu_id, nilai in per_menu.items()
        ]

    @api.model
    def hitung_kebutuhan_bahan(self, menu_id, estimasi_porsi):
        bom = self.env['mrp.bom'].search(
            [('product_tmpl_id', '=', menu_id)], limit=1)
        hasil = []
        for line in bom.bom_line_ids:
            hasil.append({
                'id_bahan': line.product_id.id,
                'nama_bahan': line.product_id.name,
                'kebutuhan_kotor': line.product_qty * estimasi_porsi,
            })
        return hasil

    @api.model
    def hitung_rekomendasi_pengadaan(self, kebutuhan_kotor, stok_aktual):
        return max(0.0, kebutuhan_kotor - stok_aktual)


class GumijusServiceDashboard(models.AbstractModel):
    _name = 'gumijus.service.dashboard'
    _description = 'Layanan Dashboard'

    @api.model
    def _data(self, cabang_id=False, periode=False, bahan_id=False):
        return self.env['gumijus.rekomendasi'].get_dashboard_data(
            cabang_id, periode, bahan_id)

    @api.model
    def tampilkan_estimasi(self, cabang_id=False, periode=False, bahan_id=False):
        data = self._data(cabang_id, periode, bahan_id)
        return {
            'trend_labels': data['trend_labels'],
            'trend_series': data['trend_series'],
            'model_status': data['model_status'],
            'model_version': data['model_version'],
        }

    @api.model
    def tampilkan_status_stok(self, cabang_id=False, periode=False, bahan_id=False):
        return self._data(cabang_id, periode, bahan_id)['stock_summary']

    @api.model
    def tampilkan_cuaca_dan_rekomendasi(self, cabang_id=False, periode=False, bahan_id=False):
        data = self._data(cabang_id, periode, bahan_id)
        return {
            'weather': data['weather'],
            'procurement': data['procurement'],
        }


class GumijusServiceEvaluasiDanModel(models.AbstractModel):
    _name = 'gumijus.service.evaluasi.model'
    _description = 'Layanan Evaluasi dan Model'

    @api.model
    def hitung_deviasi_dan_wape(self, evaluasi_id):
        evaluasi = self.env['gumijus.evaluasi'].browse(evaluasi_id)
        return {
            'deviasi_total': evaluasi.deviasi_total,
            'nilai_wape': evaluasi.nilai_wape,
        }

    @api.model
    def validasi_ambang(self, evaluasi_id):
        evaluasi = self.env['gumijus.evaluasi'].browse(evaluasi_id)
        return {
            'nilai_wape': evaluasi.nilai_wape,
            'ambang_batas': evaluasi.ambang_batas,
            'perlu_retrain': evaluasi.perlu_retrain,
            'status_model': evaluasi.status_model,
        }

    @api.model
    def latih_ulang_model(self, pelatihan_id):
        pelatihan = self.env['gumijus.pelatihan'].browse(pelatihan_id)
        pelatihan.action_latih()
        return {
            'status': pelatihan.status,
            'versi_model': pelatihan.versi_model,
            'wape_per_cabang': [
                {
                    'id_cabang': line.id_cabang.id,
                    'nilai_wape': line.nilai_wape,
                    'status': line.status,
                }
                for line in pelatihan.line_ids
            ],
        }

    @api.model
    def perbarui_parameter(self, pelatihan_id, versi_model=False):
        pelatihan = self.env['gumijus.pelatihan'].browse(pelatihan_id)
        if versi_model:
            pelatihan.versi_model = versi_model
        pelatihan.action_simpan_versi()
        return pelatihan.versi_model
