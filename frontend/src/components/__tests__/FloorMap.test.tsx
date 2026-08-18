import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FloorMap } from "../FloorMap";
import { getDestinationLabelLayout } from "../floorMapLayout";

const FLOOR = {
  floor: 3,
  floorplan: {
    type: "zones_rect" as const,
    width: 100,
    height: 100,
    zones_rect: [{ zone: "C", x: 60, y: 5, w: 35, h: 35 }],
  },
  zones: [{ zone: "C", floor: 3, x: 80, y: 20 }],
  waypoints: [
    { id: "stairs", floor: 3, x: 50, y: 50, type: "階段" },
    { id: "ev", floor: 3, x: 58, y: 50, type: "EV" },
  ],
  edges: [],
  sub_passages: [],
};

describe("FloorMap", () => {
  it("商品名を所属ゾーン内に省略表示し、完全な名称はtitleとaria-labelに残す", () => {
    const destination = {
      productId: "P-RIGHT",
      name: "防音・抗菌防臭・防ダニ・防炎カーペット",
      x: 77,
      y: 18,
      order: 1,
    };

    const layout = getDestinationLabelLayout(destination, 100, 100, FLOOR.floorplan.zones_rect[0]);
    expect(layout.textAnchor).toBe("middle");
    expect(layout.x).toBeGreaterThanOrEqual(60);
    expect(layout.x).toBeLessThanOrEqual(95);
    expect(layout.y).toBeGreaterThan(destination.y);
    expect(layout.text).toMatch(/…$/);

    render(<FloorMap floorData={FLOOR} destinations={[destination]} />);

    expect(screen.getByTestId("route-destination-label-P-RIGHT")).toHaveAttribute("text-anchor", "middle");
    expect(screen.getByLabelText(`1. ${destination.name}`)).toBeInTheDocument();
    expect(screen.getByText(`1. ${destination.name}`)).toBeInTheDocument();
  });

  it("ルート線を階段・EVの下層に描き、施設ラベルを左右へ分ける", () => {
    render(
      <FloorMap
        floorData={FLOOR}
        routeWaypoints={[
          { floor: 3, x: 30, y: 50, type: "通路" },
          { floor: 3, x: 70, y: 50, type: "通路" },
        ]}
      />,
    );

    const route = screen.getByTestId("route-line");
    const stairs = screen.getByTestId("waypoint-group-階段");
    const ev = screen.getByTestId("waypoint-group-EV");
    expect(route.compareDocumentPosition(stairs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(route.compareDocumentPosition(ev) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("階段")).toHaveAttribute("text-anchor", "end");
    expect(screen.getByText("EV")).toHaveAttribute("text-anchor", "start");
  });
});
