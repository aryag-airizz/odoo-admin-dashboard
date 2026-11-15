
/** @odoo-module **/

import { Component, onWillStart, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class SuperadminDashboard extends Component {
    static template = "superadmin_dashboard.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = proxy({
            loading: true,
            stats: {
                total_companies: 0,
                active_companies: 0,
                total_databases: 0,
                production_databases: 0,
            },
        });

        onWillStart(async () => {
            this.state.stats = await this.orm.call(
                "superadmin.dashboard",
                "get_dashboard_data",
                []
            );
            this.state.loading = false;
        });
    }

    openCompanies() {
        this.action.doAction(
            "superadmin_dashboard.action_superadmin_companies"
        );
    }

    openDatabases() {
        this.action.doAction(
            "superadmin_dashboard.action_superadmin_databases"
        );
    }
}

registry.category("actions").add(
    "superadmin_dashboard.dashboard",
    SuperadminDashboard
);
