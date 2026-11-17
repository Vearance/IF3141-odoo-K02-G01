def post_init_hook(env):
    env.cr.execute("""
        CREATE OR REPLACE VIEW gumijus_rekap_stok AS
        SELECT row_number() OVER (ORDER BY id_cabang, id_bahan) AS id,
               id_cabang,
               id_bahan,
               SUM(jml_masuk) AS jml_masuk,
               SUM(jml_pakai) AS jml_pakai,
               (ARRAY_AGG(sisa_stok ORDER BY tanggal DESC))[1] AS sisa_stok
        FROM gumijus_stok_harian
        GROUP BY id_cabang, id_bahan
    """)
