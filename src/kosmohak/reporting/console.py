from kosmohak.domain.result import SimulationResult


def format_result(result: SimulationResult) -> str:
    summary = result.summary
    lines = [
        f"PLAN: {summary['plan_id']}",
        f"SCENARIO: {summary['scenario_id']}",
        f"VALID: {'YES' if summary['valid'] else 'NO'}",
        f"Undiscounted cost: {summary['undiscounted_cost_mln']:.3f} mln units",
        f"Discounted cost: {summary['discounted_cost_mln']:.3f} mln units",
        f"Total shortage: {summary['total_shortage_t']:.3f} t",
        f"Final inventory: {summary['final_inventory_t']:.3f} t",
        "",
        "ANNUAL SERVICE AND COSTS:",
    ]
    for row in result.annual:
        lines.append(
            f"{row['year']} total={row['total_service_level']:.2%} "
            f"critical={row['critical_service_level']:.2%} "
            f"shortage={row['shortage_t']:.3f} t inventory={row['closing_inventory_t']:.3f} t "
            f"cost={row['total_cost_mln']:.3f}"
        )
    active = sorted(
        {
            investment
            for row in result.monthly
            for investment in row["active_investments"]
        }
    )
    lines.extend(["", f"ACTIVE INVESTMENTS: {', '.join(active) if active else 'None'}", "", "VIOLATIONS:"])
    if not result.violations:
        lines.append("None")
    for item in result.violations:
        source = f" source={item.source_id}" if item.source_id else ""
        lines.append(
            f"[{item.period}] {item.code}{source} ({item.severity}): "
            f"actual={item.actual} {item.operator} limit={item.limit} {item.unit}; "
            f"gap/excess={item.excess_or_gap}; {item.reason}"
        )
    return "\n".join(lines)

