{
    'name': 'Gumijus Prediction and Operations',
    'version': '17.0.1.1.0',
    'summary': 'Layar operasional dan prediksi kebutuhan bahan baku Gumijus',
    'description': 'Modul pendukung Milestone 4: stok harian, impor dataset, prediksi, rekomendasi, dashboard, evaluasi, dan pelatihan model.',
    'author': 'Kelompok 01 K02',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'stock', 'mrp'],
    'data': [
        'security/gumijus_security.xml',
        'security/ir.model.access.csv',
        'views/stok_views.xml',
        'views/import_dataset_views.xml',
        'views/prediksi_views.xml',
        'views/evaluasi_pelatihan_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'gumijus_prediction/static/src/js/dashboard.js',
            'gumijus_prediction/static/src/xml/dashboard.xml',
            'gumijus_prediction/static/src/scss/dashboard.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}
