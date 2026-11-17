/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class GumijusDashboard extends Component {
    static template = "gumijus_prediction.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            filters: { cabang: 0, periode: "", bahan: 0 },
            data: null,
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        const f = this.state.filters;
        this.state.data = await this.orm.call(
            "gumijus.rekomendasi",
            "get_dashboard_data",
            [f.cabang || false, f.periode || false, f.bahan || false]
        );
        if (!this.state.filters.periode && this.state.data.periode_options.length) {
            this.state.filters.periode = this.state.data.periode_options[0].value;
            return this.loadData();
        }
        this.state.loading = false;
    }

    async onFilterChange(ev) {
        const name = ev.target.name;
        let value = ev.target.value;
        if (name === "cabang" || name === "bahan") {
            value = value ? parseInt(value, 10) : 0;
        }
        this.state.filters[name] = value;
        await this.loadData();
    }

    chartPoints(series) {
        const data = this.state.data;
        if (!data || !series.values.length) {
            return "";
        }
        const max = Math.max(1, ...data.trend_series.flatMap((s) => s.values));
        const n = series.values.length;
        const left = 46;
        const right = 590;
        const top = 18;
        const bottom = 190;
        return series.values
            .map((value, index) => {
                const x = n === 1 ? left : left + ((right - left) * index) / (n - 1);
                const y = bottom - ((bottom - top) * value) / max;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join(" ");
    }

    chartDots(series) {
        const data = this.state.data;
        if (!data || !series.values.length) {
            return [];
        }
        const max = Math.max(1, ...data.trend_series.flatMap((s) => s.values));
        const n = series.values.length;
        const left = 46;
        const right = 590;
        const top = 18;
        const bottom = 190;
        return series.values.map((value, index) => ({
            x: n === 1 ? left : left + ((right - left) * index) / (n - 1),
            y: bottom - ((bottom - top) * value) / max,
            value,
        }));
    }

    total(key) {
        if (!this.state.data) {
            return 0;
        }
        return this.state.data.procurement.reduce((acc, row) => acc + (row[key] || 0), 0);
    }

    formatNumber(value) {
        return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(value || 0);
    }
}

registry.category("actions").add("gumijus_dashboard", GumijusDashboard);
