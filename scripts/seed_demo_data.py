import base64
import csv
import io
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- company & language
admin = env.ref('base.user_admin')
lang_code = 'id_ID' if env['res.lang'].search([('code', '=', 'id_ID'), ('active', '=', True)], limit=1) else 'en_US'
admin.write({'lang': lang_code, 'password': 'admin'})
idr = env.ref('base.IDR', raise_if_not_found=False)
company = env.company
company.write({'name': 'Gumijus'})
if idr and company.currency_id != idr:
    try:
        company.write({'currency_id': idr.id})
    except Exception as exc:
        print('Currency change skipped:', exc)

# ---------------------------------------------------------------- groups
group_staf = env.ref('gumijus_prediction.group_gumijus_staf')
group_pjo = env.ref('gumijus_prediction.group_gumijus_pjo')
group_cofounder = env.ref('gumijus_prediction.group_gumijus_cofounder')
group_pengembang = env.ref('gumijus_prediction.group_gumijus_pengembang')
for grp in (group_pjo, group_cofounder, group_pengembang):
    grp.write({'users': [(4, admin.id)]})

# ---------------------------------------------------------------- warehouses
wh_tubagus = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
wh_tubagus.write({'name': 'Tubagus Ismail', 'code': 'TBI'})
wh_sukajadi = env['stock.warehouse'].search([('code', '=', 'SKJ')], limit=1)
if not wh_sukajadi:
    wh_sukajadi = env['stock.warehouse'].create({'name': 'Sukajadi', 'code': 'SKJ', 'company_id': company.id})
wh_buah = env['stock.warehouse'].search([('code', '=', 'BBT')], limit=1)
if not wh_buah:
    wh_buah = env['stock.warehouse'].create({'name': 'Buah Batu', 'code': 'BBT', 'company_id': company.id})
wh_geger = env['stock.warehouse'].search([('code', '=', 'GKL')], limit=1)
if not wh_geger:
    wh_geger = env['stock.warehouse'].create({'name': 'Gegerkalong', 'code': 'GKL', 'company_id': company.id})
warehouses = [wh_tubagus, wh_sukajadi, wh_buah, wh_geger]
print('Warehouses:', [(w.name, w.code, w.lot_stock_id.complete_name) for w in warehouses])

# ---------------------------------------------------------------- categories
categ_all = env.ref('product.product_category_all')
categ_raw = env['product.category'].search([('name', '=', 'Bahan Baku')], limit=1)
if not categ_raw:
    categ_raw = env['product.category'].create({'name': 'Bahan Baku', 'parent_id': categ_all.id})
categ_menu = env['product.category'].search([('name', '=', 'Menu Jus')], limit=1)
if not categ_menu:
    categ_menu = env['product.category'].create({'name': 'Menu Jus', 'parent_id': categ_all.id})

# ---------------------------------------------------------------- uom & vendor
kg = env.ref('uom.product_uom_kgm')
litre = env.ref('uom.product_uom_litre')
unit = env.ref('uom.product_uom_unit')
vendor = env['res.partner'].search([('name', '=', 'Pasar Induk Caringin')], limit=1)
if not vendor:
    vendor = env['res.partner'].create({'name': 'Pasar Induk Caringin', 'city': 'Bandung'})

# ---------------------------------------------------------------- products
def make_product(code, name, categ, uom, cost, price, shelf, note, finished=False):
    tmpl = env['product.template'].search([('default_code', '=', code)], limit=1)
    vals = {
        'name': name,
        'default_code': code,
        'categ_id': categ.id,
        'detailed_type': 'product',
        'uom_id': uom.id,
        'uom_po_id': uom.id,
        'standard_price': cost,
        'list_price': price,
        'batas_harga': round(cost * 1.15, 2),
        'sale_ok': finished,
        'purchase_ok': not finished,
        'masa_simpan_hari': shelf,
        'catatan_penyimpanan': note,
    }
    if tmpl:
        tmpl.write(vals)
    else:
        tmpl = env['product.template'].create(vals)
    return tmpl

raw_data = [
    ('BHN-001', 'Mangga Harum Manis', kg, 18000, 0, 5, 'Simpan pada suhu 10-12°C, hindari benturan.'),
    ('BHN-002', 'Jeruk Peras', kg, 15000, 0, 7, 'Simpan di tempat sejuk dan kering.'),
    ('BHN-003', 'Apel Fuji', kg, 25000, 0, 14, 'Simpan pada chiller 4-8°C.'),
    ('BHN-004', 'Semangka Merah', kg, 8000, 0, 7, 'Potong setelah dingin, simpan tertutup.'),
    ('BHN-005', 'Nanas Madu', kg, 12000, 0, 5, 'Simpan pada suhu ruang, jauhkan dari sinar matahari.'),
    ('BHN-006', 'Gula Cair', litre, 12000, 0, 180, 'Simpan dalam wadah tertutup pada suhu ruang.'),
    ('BHN-007', 'Es Batu', kg, 2000, 0, 2, 'Simpan di freezer -18°C.'),
    ('BHN-008', 'Cup Plastik 500 ml', unit, 500, 0, 365, 'Simpan di rak kering dan bersih.'),
]
raw = {}
for code, name, uom, cost, price, shelf, note in raw_data:
    tmpl = make_product(code, name, categ_raw, uom, cost, price or cost * 1.2, shelf, note)
    raw[code] = tmpl
    print('Raw:', tmpl.name, tmpl.product_variant_id.id, tmpl.uom_id.name)

menu_data = [
    ('MNU-001', 'Jus Mangga', 17000, 6200, 2),
    ('MNU-002', 'Jus Jeruk', 15000, 5600, 2),
    ('MNU-003', 'Jus Apel', 18000, 7000, 2),
    ('MNU-004', 'Jus Semangka', 15000, 5400, 2),
    ('MNU-005', 'Jus Nanas', 16000, 5800, 2),
]
menu = {}
for code, name, price, cost, shelf in menu_data:
    tmpl = make_product(code, name, categ_menu, unit, cost, price, shelf,
                        'Produk jadi disajikan dingin; simpan maksimal 2 hari di chiller.', finished=True)
    menu[code] = tmpl
    print('Menu:', tmpl.name, tmpl.product_variant_id.id)

# ---------------------------------------------------------------- BoM
bom_spec = {
    'MNU-001': [('BHN-001', 0.20), ('BHN-006', 0.03), ('BHN-007', 0.10), ('BHN-008', 1.0)],
    'MNU-002': [('BHN-002', 0.25), ('BHN-006', 0.03), ('BHN-007', 0.10), ('BHN-008', 1.0)],
    'MNU-003': [('BHN-003', 0.22), ('BHN-006', 0.03), ('BHN-007', 0.10), ('BHN-008', 1.0)],
    'MNU-004': [('BHN-004', 0.30), ('BHN-006', 0.03), ('BHN-007', 0.10), ('BHN-008', 1.0)],
    'MNU-005': [('BHN-005', 0.25), ('BHN-006', 0.03), ('BHN-007', 0.10), ('BHN-008', 1.0)],
}
boms = {}
for menu_code, lines in bom_spec.items():
    tmpl = menu[menu_code]
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', tmpl.id)], limit=1)
    vals = {
        'product_tmpl_id': tmpl.id,
        'product_qty': 1.0,
        'product_uom_id': unit.id,
        'type': 'normal',
        'code': 'BOM-%s' % menu_code,
        'bom_line_ids': [(5, 0, 0)] + [(0, 0, {
            'product_id': raw[raw_code].product_variant_id.id,
            'product_qty': qty,
            'product_uom_id': raw[raw_code].uom_id.id,
        }) for raw_code, qty in lines],
    }
    if bom:
        bom.write(vals)
    else:
        bom = env['mrp.bom'].create(vals)
    boms[menu_code] = bom
    print('BoM:', tmpl.name, len(bom.bom_line_ids), 'lines')

# ---------------------------------------------------------------- stock quants
stock_spec = {
    'BHN-001': (120, 100, 95, 70),
    'BHN-002': (90, 85, 80, 65),
    'BHN-003': (75, 65, 60, 45),
    'BHN-004': (110, 90, 85, 60),
    'BHN-005': (65, 55, 55, 40),
    'BHN-006': (80, 75, 70, 55),
    'BHN-007': (150, 130, 120, 90),
    'BHN-008': (2500, 2200, 2000, 1600),
}
for code, qtys in stock_spec.items():
    product = raw[code].product_variant_id
    for wh, qty in zip(warehouses, qtys):
        env['stock.quant']._update_available_quantity(product, wh.lot_stock_id, qty)
for code in menu:
    product = menu[code].product_variant_id
    for wh, qty in zip(warehouses, (30, 26, 22, 15)):
        env['stock.quant']._update_available_quantity(product, wh.lot_stock_id, qty)

# ---------------------------------------------------------------- receipts
def create_picking(wh, lines, origin, done=False, date_value=None):
    src = wh.in_type_id.default_location_src_id or env.ref('stock.stock_location_suppliers')
    dest = wh.in_type_id.default_location_dest_id or wh.lot_stock_id
    picking = env['stock.picking'].create({
        'picking_type_id': wh.in_type_id.id,
        'location_id': src.id,
        'location_dest_id': dest.id,
        'partner_id': vendor.id,
        'origin': origin,
        'scheduled_date': date_value or datetime(2026, 11, 5, 8, 0),
        'move_ids': [(0, 0, {
            'name': raw[code].name,
            'product_id': raw[code].product_variant_id.id,
            'product_uom_qty': qty,
            'product_uom': raw[code].uom_id.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
        }) for code, qty in lines],
    })
    picking.action_confirm()
    picking.action_assign()
    if done:
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        try:
            picking.with_context(skip_backorder=True).button_validate()
        except Exception as exc:
            print('Receipt validation warning:', exc)
    return picking

try:
    done_receipt = create_picking(
        wh_tubagus,
        [('BHN-001', 40), ('BHN-002', 30), ('BHN-006', 20), ('BHN-008', 500)],
        'PO/TBI/2026/11/001', done=True, date_value=datetime(2026, 11, 3, 8, 0))
    print('Done receipt:', done_receipt.name, done_receipt.state)
except Exception as exc:
    print('Done receipt failed:', exc)

try:
    ready_receipt = create_picking(
        wh_tubagus,
        [('BHN-003', 25), ('BHN-004', 35), ('BHN-007', 40)],
        'PO/TBI/2026/11/002', done=False, date_value=datetime(2026, 11, 8, 8, 0))
    print('Ready receipt:', ready_receipt.name, ready_receipt.state)
except Exception as exc:
    print('Ready receipt failed:', exc)

# ---------------------------------------------------------------- manufacturing orders (usage)
def create_mo(wh, menu_code, qty, date_start):
    tmpl = menu[menu_code]
    bom = boms[menu_code]
    mo = env['mrp.production'].create({
        'product_id': tmpl.product_variant_id.id,
        'product_qty': qty,
        'product_uom_id': unit.id,
        'bom_id': bom.id,
        'date_start': date_start,
    })
    mo.action_confirm()
    mo.action_assign()
    for move in mo.move_raw_ids:
        move.quantity = move.product_uom_qty
        move.picked = True
    for move in mo.move_finished_ids:
        move.quantity = move.product_uom_qty
        move.picked = True
    try:
        mo.button_mark_done()
    except Exception as exc:
        print('MO completion warning:', exc)
    return mo

for wh, code, qty, dt in [
    (wh_tubagus, 'MNU-001', 50, datetime(2026, 11, 5, 8, 0)),
    (wh_sukajadi, 'MNU-002', 35, datetime(2026, 11, 5, 9, 0)),
    (wh_buah, 'MNU-004', 30, datetime(2026, 11, 6, 8, 0)),
    (wh_geger, 'MNU-005', 25, datetime(2026, 11, 6, 9, 0)),
]:
    try:
        mo = create_mo(wh, code, qty, dt)
        print('MO:', mo.name, mo.state)
    except Exception as exc:
        print('MO failed:', exc)

# ---------------------------------------------------------------- daily stock
for wh_idx, wh in enumerate(warehouses):
    for code, qtys in stock_spec.items():
        product = raw[code].product_variant_id
        base = max(1.0, qtys[wh_idx] / 8.0)
        for idx, day in enumerate((date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6))):
            masuk = round(base * (0.8 + 0.1 * idx), 2)
            pakai = round(base * (0.5 + 0.08 * idx), 2)
            saldo = round(base * 1.2, 2)
            rec = env['gumijus.stok.harian'].search([
                ('tanggal', '=', day), ('id_cabang', '=', wh.id), ('id_bahan', '=', product.id)
            ], limit=1)
            vals = {
                'tanggal': day,
                'id_cabang': wh.id,
                'id_bahan': product.id,
                'saldo_awal': saldo,
                'jml_masuk': masuk,
                'jml_pakai': pakai,
                'status_closing': 'closing' if day == date(2026, 11, 6) else 'draft',
                'catatan': 'Closing harian cabang %s' % wh.name if day == date(2026, 11, 6) else False,
            }
            if rec:
                rec.write(vals)
            else:
                env['gumijus.stok.harian'].create(vals)

# ---------------------------------------------------------------- dataset
menu_codes = list(menu.keys())
for wh_idx, wh in enumerate(warehouses):
    branch_factor = [1.0, 0.90, 0.82, 0.70][wh_idx]
    for day_idx in range(12):
        day = date(2026, 10, 25) + timedelta(days=day_idx)
        weekday_factor = 1.15 if day.weekday() >= 5 else 1.0
        weather = env['gumijus.dataset'].search([
            ('tanggal', '=', day), ('id_cabang', '=', wh.id), ('sumber', '=', 'Cuaca')
        ], limit=1)
        suhu = round(25 + wh_idx * 1.2 + (day_idx % 5) * 0.8, 1)
        hujan = round([0, 0, 4.5, 9.0, 0, 2.5, 12.0][(day_idx + wh_idx) % 7], 1)
        weather_vals = {
            'tanggal': day,
            'id_cabang': wh.id,
            'id_bahan': False,
            'est_porsi_terjual': 0,
            'suhu': suhu,
            'curah_hujan': hujan,
            'sumber': 'Cuaca',
            'status_validasi': 'valid',
        }
        if weather:
            weather.write(weather_vals)
        else:
            env['gumijus.dataset'].create(weather_vals)
        for menu_idx, code in enumerate(menu_codes):
            porsi = round((42 + menu_idx * 7) * branch_factor * weekday_factor + (day_idx % 4) * 2, 0)
            rec = env['gumijus.dataset'].search([
                ('tanggal', '=', day), ('id_cabang', '=', wh.id),
                ('id_bahan', '=', menu[code].product_variant_id.id), ('sumber', '=', 'Penjualan')
            ], limit=1)
            vals = {
                'tanggal': day,
                'id_cabang': wh.id,
                'id_bahan': menu[code].product_variant_id.id,
                'est_porsi_terjual': porsi,
                'suhu': suhu,
                'curah_hujan': hujan,
                'sumber': 'Penjualan',
                'status_validasi': 'valid',
            }
            if rec:
                rec.write(vals)
            else:
                env['gumijus.dataset'].create(vals)

# ---------------------------------------------------------------- import logs
def b64(text):
    return base64.b64encode(text.encode('utf-8')).decode('ascii')

penjualan_header = 'tanggal,id_cabang,menu,jml_penjualan\n'
penjualan_rows = '\n'.join('%s,%s,%s,%d' % (
    (date(2026, 11, 1) + timedelta(days=i)).isoformat(), 'TBI', 'Jus Mangga', 40 + i
) for i in range(12))
valid_penjualan = penjualan_header + penjualan_rows + '\n'

stok_bom_bad = 'id_bahan,stok\nMangga Harum Manis,120\nJeruk Peras,90\n'
valid_cuaca = 'tanggal,id_cabang,suhu,curah_hujan\n' + '\n'.join(
    '%s,TBI,%.1f,%.1f' % ((date(2026, 11, 1) + timedelta(days=i)).isoformat(), 26 + i * 0.2, [0, 3, 8][i % 3])
    for i in range(12)
) + '\n'
neg_rows = []
for i in range(13):
    neg_rows.append('%s,GKL,Jus Jeruk,%d' % ((date(2026, 11, 1) + timedelta(days=i)).isoformat(), 30 + i))
neg_rows.append('2026-11-14,GKL,Jus Jeruk,-12')
neg_penjualan = penjualan_header + '\n'.join(neg_rows) + '\n'

import_specs = [
    ('Impor Penjualan November 2026', 'penjualan', wh_tubagus, 'penjualan_november_2026.csv', valid_penjualan, 'valid', 12, False),
    ('Impor Stok dan BoM Minggu 45', 'stok_bom', wh_tubagus, 'stok_bom_minggu45.csv', stok_bom_bad, 'ditolak', 0,
     "Kolom 'kuantitas_per_porsi' tidak ditemukan pada baris 1. Kolom wajib: 'id_bahan', 'kuantitas_per_porsi', 'stok'."),
    ('Impor Penjualan Harian Gegerkalong', 'penjualan', wh_geger, 'penjualan_harian_gegerkalong.csv', neg_penjualan, 'ditolak', 14,
     "Kolom 'jml_penjualan' pada baris 14 bernilai negatif (-12.00)."),
    ('Impor Cuaca BMKG November 2026', 'cuaca', wh_tubagus, 'cuaca_november_2026.csv', valid_cuaca, 'valid', 12, False),
]
for name, jenis, wh, filename, content, status, jumlah, pesan in import_specs:
    rec = env['gumijus.import.log'].search([('name', '=', name)], limit=1)
    vals = {
        'name': name,
        'jenis_berkas': jenis,
        'id_cabang': wh.id,
        'file_name': filename,
        'file_data': b64(content),
        'tanggal_impor': datetime(2026, 11, 6, 10, 0),
        'status': status,
        'jumlah_baris': jumlah,
        'pesan_galat': pesan,
    }
    if rec:
        rec.write(vals)
    else:
        env['gumijus.import.log'].create(vals)

# ---------------------------------------------------------------- predictions
prediksi_map = {}
for wh in warehouses:
    name = 'Prediksi Kebutuhan Bahan Baku November 2026 - %s' % wh.name
    rec = env['gumijus.prediksi'].search([('name', '=', name)], limit=1)
    vals = {
        'name': name,
        'periode_mulai': date(2026, 11, 1),
        'periode_selesai': date(2026, 11, 30),
        'id_cabang': wh.id,
        'versi_model': 'v1.4.0',
        'status': 'selesai',
        'tanggal_jalan': datetime(2026, 11, 6, 9, 30),
        'catatan': 'Prediksi menggunakan data penjualan dan cuaca yang telah dibersihkan.',
    }
    if rec:
        rec.write(vals)
    else:
        rec = env['gumijus.prediksi'].create(vals)
    prediksi_map[wh.id] = rec

# draft prediction for the run-prediction screen (S-10)
draft_name = 'Prediksi Kebutuhan Bahan Baku Desember 2026 - %s' % wh_tubagus.name
draft = env['gumijus.prediksi'].search([('name', '=', draft_name)], limit=1)
draft_vals = {
    'name': draft_name,
    'periode_mulai': date(2026, 12, 1),
    'periode_selesai': date(2026, 12, 31),
    'id_cabang': wh_tubagus.id,
    'versi_model': 'v1.4.0',
    'status': 'draft',
    'catatan': 'Rencana prediksi awal Desember 2026 berdasarkan dataset tervalidasi.',
}
if draft:
    draft.write(draft_vals)
else:
    draft = env['gumijus.prediksi'].create(draft_vals)

# ---------------------------------------------------------------- recommendations
base_need = {
    'BHN-001': 48.0, 'BHN-002': 42.0, 'BHN-003': 36.0, 'BHN-004': 52.0,
    'BHN-005': 32.0, 'BHN-006': 13.0, 'BHN-007': 65.0, 'BHN-008': 950.0,
}
month_factors = [(date(2026, 8, 1), 0.90), (date(2026, 9, 1), 0.95),
                 (date(2026, 10, 1), 1.00), (date(2026, 11, 1), 1.05)]
branch_factors = {wh_tubagus.id: 1.0, wh_sukajadi.id: 0.90, wh_buah.id: 0.82, wh_geger.id: 0.70}
for wh in warehouses:
    for period, mfactor in month_factors:
        for code in raw:
            estimate = round(base_need[code] * branch_factors[wh.id] * mfactor, 2)
            stok = round(estimate * (0.60 if (int(code[-1]) + period.month) % 3 == 0 else 1.15), 2)
            rec = env['gumijus.rekomendasi'].search([
                ('periode', '=', period), ('id_cabang', '=', wh.id), ('id_bahan', '=', raw[code].product_variant_id.id)
            ], limit=1)
            vals = {
                'periode': period,
                'id_cabang': wh.id,
                'id_bahan': raw[code].product_variant_id.id,
                'prediksi_id': prediksi_map[wh.id].id if period == date(2026, 11, 1) else False,
                'est_porsi_terjual': round(estimate / max(0.001, 0.20), 0),
                'estimasi_kebutuhan': estimate,
                'stok_saat_ini': stok,
            }
            if rec:
                rec.write(vals)
            else:
                env['gumijus.rekomendasi'].create(vals)

# ---------------------------------------------------------------- evaluation
eval_specs = [
    (wh_tubagus, 12500, 11800, 18.4),
    (wh_sukajadi, 10500, 10200, 20.7),
    (wh_buah, 9800, 10100, 22.1),
    (wh_geger, 7900, 8350, 27.6),
]
for wh, aktual, prediksi, wape in eval_specs:
    name = 'Evaluasi Akurasi Oktober 2026 - %s' % wh.name
    rec = env['gumijus.evaluasi'].search([('name', '=', name)], limit=1)
    vals = {
        'name': name,
        'periode_mulai': date(2026, 10, 1),
        'periode_selesai': date(2026, 10, 31),
        'id_cabang': wh.id,
        'total_aktual': aktual,
        'total_prediksi': prediksi,
        'nilai_wape': wape,
        'ambang_batas': 25.0,
        'catatan': 'WAPE dihitung dari total porsi terjual aktual dan hasil prediksi.',
    }
    if rec:
        rec.write(vals)
    else:
        env['gumijus.evaluasi'].create(vals)

# ---------------------------------------------------------------- training
tr_name = 'Pelatihan Ulang Model v1.4.0'
tr = env['gumijus.pelatihan'].search([('name', '=', tr_name)], limit=1)
tr_vals = {
    'name': tr_name,
    'tanggal': datetime(2026, 11, 6, 8, 0),
    'periode_data': 'Agustus - Oktober 2026',
    'versi_model': 'v1.4.0',
    'split_train': 80,
    'split_test': 20,
    'total_data': 2880,
    'status': 'selesai',
}
if tr:
    tr.write(tr_vals)
else:
    tr = env['gumijus.pelatihan'].create(tr_vals)
tr.line_ids.unlink()
for wh, wape in [(wh_tubagus, 17.8), (wh_sukajadi, 20.2), (wh_buah, 21.4), (wh_geger, 24.6)]:
    env['gumijus.pelatihan.line'].create({
        'pelatihan_id': tr.id,
        'id_cabang': wh.id,
        'nilai_wape': wape,
        'ambang_batas': 25.0,
    })

# ---------------------------------------------------------------- users
def ensure_user(login, name, groups, cabang=False):
    user = env['res.users'].search([('login', '=', login)], limit=1)
    group_ids = [env.ref(x).id for x in groups]
    vals = {
        'name': name,
        'login': login,
        'password': 'gumijus123',
        'email': '%s@gumijus.example' % login,
        'lang': lang_code,
        'company_id': company.id,
        'company_ids': [(6, 0, [company.id])],
        'groups_id': [(6, 0, group_ids)],
        'gumijus_cabang_id': cabang.id if cabang else False,
    }
    if user:
        user.write(vals)
    else:
        user = env['res.users'].create(vals)
    print('User:', user.login, user.name, user.gumijus_cabang_id.name)

ensure_user('staf_tubagus', 'Staf Cabang Tubagus Ismail (JB-04)',
            ['base.group_user', 'stock.group_stock_user', 'gumijus_prediction.group_gumijus_staf'], wh_tubagus)
ensure_user('pjo', 'Penanggung Jawab Operasional (JB-02)',
            ['base.group_user', 'stock.group_stock_manager', 'mrp.group_mrp_manager',
             'gumijus_prediction.group_gumijus_pjo'])
ensure_user('cofounder', 'Co-founder (JB-01)',
            ['base.group_user', 'stock.group_stock_user', 'gumijus_prediction.group_gumijus_cofounder'])
ensure_user('pengembang', 'Pengembang Model Prediksi (JB-05)',
            ['base.group_user', 'stock.group_stock_user', 'gumijus_prediction.group_gumijus_pengembang'])

env.cr.commit()
print('SEED DONE')
