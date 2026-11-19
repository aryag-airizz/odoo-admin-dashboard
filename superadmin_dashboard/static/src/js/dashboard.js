/** @odoo-module **/

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { formatDateTime, deserializeDateTime } from "@web/core/l10n/dates";

class SuperadminDashboard extends Component {
    static template = "superadmin_dashboard.Dashboard";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = proxy({
            loading: true,
            syncing: false,
            search: "",
            data: null,
        });

        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("superadmin.dashboard", "get_dashboard_data", []);
        this.state.loading = false;
    }

    async syncAll() {
        this.state.syncing = true;
        try {
            await this.orm.call("superadmin.database", "action_sync_all", []);
            await this.load();
        } finally {
            this.state.syncing = false;
        }
    }

    get filteredCompanies() {
        const q = this.state.search.trim().toLowerCase();
        const rows = this.state.data.companies;
        if (!q) {
            return rows;
        }
        return rows.filter(
            (c) => c.name.toLowerCase().includes(q) || c.database.toLowerCase().includes(q)
        );
    }

    formatDate(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "—";
    }

    formatAmount(value) {
        return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value || 0);
    }

    stateClass(db) {
        if (db.state === "connected") {
            return db.stale ? "text-bg-warning" : "text-bg-success";
        }
        return db.state === "error" ? "text-bg-danger" : "text-bg-secondary";
    }

    stateLabel(db) {
        if (db.state === "connected") {
            return db.stale ? "Stale" : "Connected";
        }
        return db.state === "error" ? "Error" : "Not synced";
    }

    registerDatabase() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "superadmin.database",
            views: [[false, "form"]],
            target: "current",
        });
    }

    openDatabase(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "superadmin.database",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openCompanies() {
        this.action.doAction("superadmin_dashboard.action_superadmin_companies");
    }

    openDatabases() {
        this.action.doAction("superadmin_dashboard.action_superadmin_databases");
    }
}

registry.category("actions").add("superadmin_dashboard.dashboard", SuperadminDashboard);
