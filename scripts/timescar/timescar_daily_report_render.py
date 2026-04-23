#!/usr/bin/env python3
from __future__ import annotations

from timescar_fetch_reservations import fetch
from task_runtime import TimesCarTaskRuntime


def main() -> int:
    runtime = TimesCarTaskRuntime("timescar-daily-report-render", "read", ttl_seconds=900)
    runtime.start("fetch-reservations")
    data = fetch(runtime=runtime)
    reservations = data.get("reservations", [])
    lines = [f"当前已预约 {len(reservations)} 单"]
    if reservations:
        lines.append("")
    for idx, reservation in enumerate(reservations, 1):
        lines.extend(
            [
                f"预约 {idx}",
                f'- 预约编号：{reservation.get("bookingNumber", "")}',
                f'- 预约开始：{reservation.get("startText", "")}',
                f'- 返却予定：{reservation.get("returnText", "")}',
                f'- ステーション：{reservation.get("station", "")}',
                f'- 车辆：{reservation.get("vehicle", "")}',
                f'- 车牌/识别：{reservation.get("carIdentifier", "")}',
                f'- 车身颜色：{reservation.get("carColor", "")}',
                f'- 预约受理时间：{reservation.get("acceptedAtText", "")}',
                f'- e-ticket：{reservation.get("eTicket", "") or "无"}',
                f'- 安心补偿服务：{reservation.get("insurance", "") or "无"}',
            ]
        )
        if idx != len(reservations):
            lines.append("")
    message = "\n".join(lines).strip()
    runtime.finish("ok", "done", final_message=message)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
