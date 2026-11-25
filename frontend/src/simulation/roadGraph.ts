export interface TrafficPoint {
  x: number;
  z: number;
}

export interface TrafficPath {
  points: TrafficPoint[];
  cumulative: number[];
  total: number;
}

export interface TrafficSample {
  x: number;
  z: number;
  yaw: number;
}

function buildTrafficPath(rawPoints: TrafficPoint[]): TrafficPath {
  const points = rawPoints.map((point) => ({ ...point }));
  const first = points[0];
  const last = points[points.length - 1];
  if (first && last && (first.x !== last.x || first.z !== last.z)) {
    points.push({ ...first });
  }

  const cumulative = [0];
  for (let i = 1; i < points.length; i += 1) {
    const previous = points[i - 1];
    const current = points[i];
    cumulative.push(cumulative[i - 1] + Math.hypot(current.x - previous.x, current.z - previous.z));
  }
  return { points, cumulative, total: cumulative[cumulative.length - 1] || 0 };
}

export function sampleTrafficPath(path: TrafficPath, distance: number): TrafficSample {
  if (path.points.length < 2 || path.total <= 0) {
    return { x: path.points[0]?.x ?? 0, z: path.points[0]?.z ?? 0, yaw: 0 };
  }

  const wrapped = ((distance % path.total) + path.total) % path.total;
  let low = 0;
  let high = path.cumulative.length - 1;
  while (low < high - 1) {
    const middle = Math.floor((low + high) / 2);
    if (path.cumulative[middle] <= wrapped) low = middle;
    else high = middle;
  }

  const start = path.points[low];
  const end = path.points[low + 1];
  const segmentLength = path.cumulative[low + 1] - path.cumulative[low] || 1;
  const alpha = (wrapped - path.cumulative[low]) / segmentLength;
  return {
    x: start.x + (end.x - start.x) * alpha,
    z: start.z + (end.z - start.z) * alpha,
    yaw: Math.atan2(end.x - start.x, end.z - start.z),
  };
}

function pushUnique(points: TrafficPoint[], point: TrafficPoint): void {
  const previous = points[points.length - 1];
  if (!previous || Math.hypot(point.x - previous.x, point.z - previous.z) > 1e-9) {
    points.push({ ...point });
  }
}

function addInwardLaneTurn(
  points: TrafficPoint[],
  start: TrafficPoint,
  end: TrafficPoint,
  tangent: Direction,
  controlDistance: number
): void {
  const segments = 32;
  for (let i = 1; i <= segments; i += 1) {
    const t = i / segments;
    const inverse = 1 - t;
    const controlA = offsetPoint(start, tangent, -controlDistance);
    const controlB = offsetPoint(end, tangent, -controlDistance);
    pushUnique(points, {
      x: inverse ** 3 * start.x + 3 * inverse ** 2 * t * controlA.x
        + 3 * inverse * t ** 2 * controlB.x + t ** 3 * end.x,
      z: inverse ** 3 * start.z + 3 * inverse ** 2 * t * controlA.z
        + 3 * inverse * t ** 2 * controlB.z + t ** 3 * end.z,
    });
  }
}

/**
 * Build a closed two-way lane loop over an arbitrary open road centerline.
 * The rendered ribbon and traffic use the same sampled curve; U-turns curl
 * inward so vehicles remain on the asphalt at both endpoints.
 */
export function buildLaneLoop(
  centerline: readonly TrafficPoint[],
  laneOffset = 7.5
): TrafficPath {
  if (centerline.length < 2) throw new RangeError("A lane loop needs at least two points.");
  if (!Number.isFinite(laneOffset) || laneOffset <= 0) {
    throw new RangeError("Lane offset must be finite and positive.");
  }

  const left: TrafficPoint[] = [];
  const right: TrafficPoint[] = [];
  centerline.forEach((point, index) => {
    const previous = centerline[Math.max(0, index - 1)];
    const next = centerline[Math.min(centerline.length - 1, index + 1)];
    const direction = directionBetween(previous, next);
    const normal = rightNormal(direction);
    left.push({ x: point.x + normal.x * laneOffset, z: point.z + normal.z * laneOffset });
    right.push({ x: point.x - normal.x * laneOffset, z: point.z - normal.z * laneOffset });
  });

  const startDirection = directionBetween(centerline[0], centerline[1]);
  const endDirection = directionBetween(
    centerline[centerline.length - 2],
    centerline[centerline.length - 1]
  );
  const points: TrafficPoint[] = [left[0]];
  for (let i = 1; i < left.length; i += 1) pushUnique(points, left[i]);
  addInwardLaneTurn(
    points,
    left[left.length - 1],
    right[right.length - 1],
    endDirection,
    laneOffset * 4 / 3
  );
  for (let i = right.length - 2; i >= 0; i -= 1) pushUnique(points, right[i]);
  addInwardLaneTurn(
    points,
    right[0],
    left[0],
    { x: -startDirection.x, z: -startDirection.z },
    laneOffset * 4 / 3
  );
  return buildTrafficPath(points);
}

function addLaneTurn(
  points: TrafficPoint[],
  start: TrafficPoint,
  end: TrafficPoint,
  direction: Direction,
  controlDistance: number
): void {
  const turnSegments = 48;
  for (let i = 1; i <= turnSegments; i += 1) {
    const t = i / turnSegments;
    const inverse = 1 - t;
    const controlA = offsetPoint(start, direction, controlDistance);
    const controlB = offsetPoint(end, direction, controlDistance);
    points.push({
      x: inverse ** 3 * start.x + 3 * inverse ** 2 * t * controlA.x
        + 3 * inverse * t ** 2 * controlB.x + t ** 3 * end.x,
      z: inverse ** 3 * start.z + 3 * inverse ** 2 * t * controlA.z
        + 3 * inverse * t ** 2 * controlB.z + t ** 3 * end.z,
    });
  }
}

export function createHighwayLoop(
  a: { x: number; z: number },
  b: { x: number; z: number },
  laneOffset = 7.5
): TrafficPath {
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const length = Math.hypot(dx, dz) || 1;
  const directionX = dx / length;
  const directionZ = dz / length;
  const normalX = -directionZ;
  const normalZ = directionX;

  const aForward = { x: a.x + normalX * laneOffset, z: a.z + normalZ * laneOffset };
  const bForward = { x: b.x + normalX * laneOffset, z: b.z + normalZ * laneOffset };
  const bReturn = { x: b.x - normalX * laneOffset, z: b.z - normalZ * laneOffset };
  const aReturn = { x: a.x - normalX * laneOffset, z: a.z - normalZ * laneOffset };
  const points: TrafficPoint[] = [aForward, bForward];

  addLaneTurn(
    points, bForward, bReturn, { x: directionX, z: directionZ }, laneOffset * 4 / 3
  );
  points.push(aReturn);
  addLaneTurn(
    points, aReturn, aForward, { x: -directionX, z: -directionZ }, laneOffset * 4 / 3
  );
  return buildTrafficPath(points);
}

export function createCityLoop(
  anchor: { x: number; z: number },
  axis: "x" | "z",
  laneOffset = 7.5,
  span = 700
): TrafficPath {
  if (axis === "x") {
    const leftForward = { x: anchor.x - span, z: anchor.z + laneOffset };
    const rightForward = { x: anchor.x + span, z: anchor.z + laneOffset };
    const rightReturn = { x: anchor.x + span, z: anchor.z - laneOffset };
    const leftReturn = { x: anchor.x - span, z: anchor.z - laneOffset };
    const points: TrafficPoint[] = [leftForward, rightForward];
    addLaneTurn(points, rightForward, rightReturn, { x: 1, z: 0 }, laneOffset * 4 / 3);
    points.push(leftReturn);
    addLaneTurn(points, leftReturn, leftForward, { x: -1, z: 0 }, laneOffset * 4 / 3);
    return buildTrafficPath(points);
  }

  const topForward = { x: anchor.x - laneOffset, z: anchor.z - span };
  const bottomForward = { x: anchor.x - laneOffset, z: anchor.z + span };
  const bottomReturn = { x: anchor.x + laneOffset, z: anchor.z + span };
  const topReturn = { x: anchor.x + laneOffset, z: anchor.z - span };
  const points: TrafficPoint[] = [topForward, bottomForward];
  addLaneTurn(points, bottomForward, bottomReturn, { x: 0, z: 1 }, laneOffset * 4 / 3);
  points.push(topReturn);
  addLaneTurn(points, topReturn, topForward, { x: 0, z: -1 }, laneOffset * 4 / 3);
  return buildTrafficPath(points);
}

/** Anchor geometry matches COUNTRY_FLAT_ANCHORS; its country radius is deliberately ignored. */
export interface OpenWorldAnchor {
  x: number;
  z: number;
  /** Existing country-sector radius; accepted for compatibility but not a hub size. */
  radius?: number;
  /** Existing biome color; accepted for compatibility and not used geometrically. */
  ground?: string;
  /** Round asphalt hub radius. Defaults to the diorama's 72 m hub. */
  hubRadius?: number;
}

export type OpenWorldHighwayLink =
  | readonly [from: string, to: string]
  | { readonly from: string; readonly to: string };

export interface OpenWorldRouteOptions {
  /** Distance from a country center to each boulevard turnaround. */
  span?: number;
  laneOffset?: number;
  hubRadius?: number;
  /** The rendered boulevard extends 825 m either side of its anchor. */
  boulevardHalfLength?: number;
  boulevardHalfWidth?: number;
  /** The rendered cross-border highway is 34 m wide. */
  highwayHalfWidth?: number;
}

interface ResolvedRouteOptions {
  span: number;
  laneOffset: number;
  hubRadius: number;
  boulevardHalfLength: number;
  boulevardHalfWidth: number;
  highwayHalfWidth: number;
}

interface RouteAnchor extends OpenWorldAnchor {
  id: string;
  hubRadius: number;
}

interface Direction {
  x: number;
  z: number;
}

const END_TURN_CONTROL = 34;
const HUB_PORT_RATIO = 0.62;
const HUB_CONTROL_RATIO = 0.32;
const HUB_CURVE_SEGMENTS = 32;
const MAX_HIGHWAY_CYCLES = 64;
const MAX_HIGHWAY_CYCLE_LENGTH = 6;

function resolveRouteOptions(options: OpenWorldRouteOptions): ResolvedRouteOptions {
  const resolved: ResolvedRouteOptions = {
    span: options.span ?? 700,
    laneOffset: options.laneOffset ?? 7.5,
    hubRadius: options.hubRadius ?? 72,
    boulevardHalfLength: options.boulevardHalfLength ?? 825,
    boulevardHalfWidth: options.boulevardHalfWidth ?? 19,
    highwayHalfWidth: options.highwayHalfWidth ?? 17,
  };
  const { laneOffset, ...dimensions } = resolved;
  if (Object.values(dimensions).some((value) => !Number.isFinite(value) || value <= 0)) {
    throw new RangeError("Open-world route dimensions must be finite and positive.");
  }
  if (!Number.isFinite(laneOffset) || laneOffset <= 0) {
    throw new RangeError("Lane offset must be finite and positive.");
  }
  if (resolved.span + END_TURN_CONTROL > resolved.boulevardHalfLength) {
    throw new RangeError("Boulevard turnarounds must fit inside the rendered road.");
  }
  if (laneOffset >= Math.min(resolved.boulevardHalfWidth, resolved.highwayHalfWidth)) {
    throw new RangeError("Lane offset must be smaller than the road half-width.");
  }
  return resolved;
}

function normalizeAnchors(
  anchors: Readonly<Record<string, OpenWorldAnchor>>,
  options: ResolvedRouteOptions
): RouteAnchor[] {
  return Object.keys(anchors)
    .sort()
    .flatMap((id) => {
      const anchor = anchors[id];
      if (!anchor || !Number.isFinite(anchor.x) || !Number.isFinite(anchor.z)) return [];
      const requestedRadius = anchor.hubRadius ?? options.hubRadius;
      const hubRadius = Number.isFinite(requestedRadius) && requestedRadius > 0
        ? Math.max(requestedRadius, options.laneOffset * 1.4 + 4)
        : options.hubRadius;
      return [{ id, x: anchor.x, z: anchor.z, hubRadius }];
    });
}

function normalizeHighwayLinks(
  links: readonly OpenWorldHighwayLink[],
  anchorIds: ReadonlySet<string>
): Array<[string, string]> {
  const unique = new Map<string, [string, string]>();
  for (const link of links) {
    const from = "from" in link ? link.from : link[0];
    const to = "from" in link ? link.to : link[1];
    if (!anchorIds.has(from) || !anchorIds.has(to) || from === to) continue;
    const key = from < to ? `${from}\u0000${to}` : `${to}\u0000${from}`;
    if (!unique.has(key)) unique.set(key, from < to ? [from, to] : [to, from]);
  }
  return [...unique.values()].sort(([a, b], [c, d]) =>
    a === c ? (b < d ? -1 : b > d ? 1 : 0) : a < c ? -1 : 1
  );
}

function directionBetween(a: TrafficPoint, b: TrafficPoint): Direction {
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const length = Math.hypot(dx, dz) || 1;
  return { x: dx / length, z: dz / length };
}

function rightNormal(direction: Direction): Direction {
  return { x: -direction.z, z: direction.x };
}

function offsetPoint(point: TrafficPoint, direction: Direction, distance: number): TrafficPoint {
  return { x: point.x + direction.x * distance, z: point.z + direction.z * distance };
}

function lanePort(
  anchor: RouteAnchor,
  direction: Direction,
  laneOffset: number,
  entering = false
): TrafficPoint {
  const normal = rightNormal(direction);
  const distance = anchor.hubRadius * HUB_PORT_RATIO * (entering ? -1 : 1);
  return {
    x: anchor.x + direction.x * distance + normal.x * laneOffset,
    z: anchor.z + direction.z * distance + normal.z * laneOffset,
  };
}

function pushPoint(points: TrafficPoint[], point: TrafficPoint): void {
  const previous = points[points.length - 1];
  if (!previous || Math.hypot(point.x - previous.x, point.z - previous.z) > 1e-9) {
    points.push({ ...point });
  }
}

function addCubic(
  points: TrafficPoint[],
  start: TrafficPoint,
  end: TrafficPoint,
  controlA: TrafficPoint,
  controlB: TrafficPoint
): void {
  for (let i = 1; i <= HUB_CURVE_SEGMENTS; i += 1) {
    const t = i / HUB_CURVE_SEGMENTS;
    const inverse = 1 - t;
    pushPoint(points, {
      x: inverse ** 3 * start.x + 3 * inverse ** 2 * t * controlA.x
        + 3 * inverse * t ** 2 * controlB.x + t ** 3 * end.x,
      z: inverse ** 3 * start.z + 3 * inverse ** 2 * t * controlA.z
        + 3 * inverse * t ** 2 * controlB.z + t ** 3 * end.z,
    });
  }
}

/** A convex cubic whose four control points are in the hub stays in the hub. */
function addHubConnector(
  points: TrafficPoint[],
  anchor: RouteAnchor,
  start: TrafficPoint,
  end: TrafficPoint,
  incoming: Direction,
  outgoing: Direction
): void {
  const controlLength = anchor.hubRadius * HUB_CONTROL_RATIO;
  addCubic(
    points,
    start,
    end,
    offsetPoint(start, incoming, controlLength),
    offsetPoint(end, outgoing, -controlLength)
  );
}

function appendHubVisit(
  points: TrafficPoint[],
  anchor: RouteAnchor,
  incoming: Direction,
  outgoing: Direction,
  excursion: { axis: "x" | "z"; sign: number } | undefined,
  options: ResolvedRouteOptions
): void {
  const entry = lanePort(anchor, incoming, options.laneOffset, true);
  const exit = lanePort(anchor, outgoing, options.laneOffset);
  pushPoint(points, entry);
  if (!excursion) {
    addHubConnector(points, anchor, entry, exit, incoming, outgoing);
    return;
  }

  const excursionDirection: Direction = excursion.axis === "x"
    ? { x: excursion.sign, z: 0 }
    : { x: 0, z: excursion.sign };
  const normal = rightNormal(excursionDirection);
  const excursionExit = lanePort(anchor, excursionDirection, options.laneOffset);
  addHubConnector(points, anchor, entry, excursionExit, incoming, excursionDirection);

  const farLane = {
    x: anchor.x + excursionDirection.x * options.span + normal.x * options.laneOffset,
    z: anchor.z + excursionDirection.z * options.span + normal.z * options.laneOffset,
  };
  const farReturn = {
    x: anchor.x + excursionDirection.x * options.span - normal.x * options.laneOffset,
    z: anchor.z + excursionDirection.z * options.span - normal.z * options.laneOffset,
  };
  pushPoint(points, farLane);
  addLaneTurn(points, farLane, farReturn, excursionDirection, options.laneOffset * 4 / 3);

  const excursionEntry = {
    x: anchor.x + excursionDirection.x * anchor.hubRadius * HUB_PORT_RATIO
      - normal.x * options.laneOffset,
    z: anchor.z + excursionDirection.z * anchor.hubRadius * HUB_PORT_RATIO
      - normal.z * options.laneOffset,
  };
  pushPoint(points, excursionEntry);
  addHubConnector(
    points, anchor, excursionEntry, exit,
    { x: -excursionDirection.x, z: -excursionDirection.z }, outgoing
  );
}

function buildHubRoute(
  anchors: readonly RouteAnchor[],
  directions: readonly Direction[],
  routeIndex: number,
  options: ResolvedRouteOptions,
  forceExcursions: boolean
): TrafficPath {
  const points: TrafficPoint[] = [];
  anchors.forEach((anchor, index) => {
    const incoming = directions[(index - 1 + anchors.length) % anchors.length];
    const outgoing = directions[index];
    const useExcursion = forceExcursions || (routeIndex + index) % 3 !== 1;
    appendHubVisit(
      points,
      anchor,
      incoming,
      outgoing,
      useExcursion
        ? { axis: (routeIndex + index) % 2 === 0 ? "x" : "z", sign: (routeIndex + index) % 4 < 2 ? 1 : -1 }
        : undefined,
      options
    );
    if (index < anchors.length - 1) {
      pushPoint(points, lanePort(anchors[index + 1], outgoing, options.laneOffset, true));
    }
  });
  // The final highway/boulevard leg meets the exact first port, so wrapping
  // distance from total to zero has neither a positional nor tangent jump.
  pushPoint(points, lanePort(anchors[0], directions[directions.length - 1], options.laneOffset, true));
  return buildTrafficPath(points);
}

function buildBoulevardLoop(
  anchor: RouteAnchor,
  axis: "x" | "z",
  options: ResolvedRouteOptions
): TrafficPath {
  const direction: Direction = axis === "x" ? { x: -1, z: 0 } : { x: 0, z: -1 };
  const normal = rightNormal(direction);
  const start = lanePort(anchor, direction, options.laneOffset);
  const points: TrafficPoint[] = [start];
  const lanePoint = (along: number, side: number): TrafficPoint => ({
    x: anchor.x + direction.x * along + normal.x * options.laneOffset * side,
    z: anchor.z + direction.z * along + normal.z * options.laneOffset * side,
  });
  const firstTurn = lanePoint(options.span, 1);
  const secondTurn = lanePoint(options.span, -1);
  const thirdTurn = lanePoint(-options.span, -1);
  const fourthTurn = lanePoint(-options.span, 1);
  const returnPort = lanePort(anchor, direction, options.laneOffset, true);

  pushPoint(points, firstTurn);
  addLaneTurn(points, firstTurn, secondTurn, direction, options.laneOffset * 4 / 3);
  pushPoint(points, thirdTurn);
  addLaneTurn(
    points, thirdTurn, fourthTurn,
    { x: -direction.x, z: -direction.z }, options.laneOffset * 4 / 3
  );
  pushPoint(points, returnPort);
  addHubConnector(points, anchor, returnPort, start, direction, direction);
  return buildTrafficPath(points);
}

function canonicalCycle(cycle: readonly string[]): string {
  const variants: string[][] = [];
  for (const direction of [cycle, [...cycle].reverse()]) {
    for (let i = 0; i < direction.length; i += 1) {
      variants.push([...direction.slice(i), ...direction.slice(0, i)]);
    }
  }
  variants.sort((a, b) => {
    const aKey = JSON.stringify(a);
    const bKey = JSON.stringify(b);
    return aKey === bKey ? 0 : aKey < bKey ? -1 : 1;
  });
  return JSON.stringify(variants[0]);
}

function findHighwayCycles(
  ids: readonly string[],
  links: readonly (readonly [string, string])[]
): string[][] {
  const adjacency = new Map(ids.map((id) => [id, [] as string[]]));
  for (const [from, to] of links) {
    adjacency.get(from)?.push(to);
    adjacency.get(to)?.push(from);
  }
  for (const neighbors of adjacency.values()) neighbors.sort();
  const cycles = new Map<string, string[]>();

  const visit = (start: string, current: string, path: string[], seen: Set<string>): void => {
    if (cycles.size >= MAX_HIGHWAY_CYCLES) return;
    for (const next of adjacency.get(current) ?? []) {
      if (next === start && path.length >= 3) {
        const key = canonicalCycle(path);
        if (!cycles.has(key)) cycles.set(key, [...path]);
      } else if (
        next > start && !seen.has(next) && path.length < MAX_HIGHWAY_CYCLE_LENGTH
      ) {
        seen.add(next);
        path.push(next);
        visit(start, next, path, seen);
        path.pop();
        seen.delete(next);
      }
    }
  };

  for (const id of ids) visit(id, id, [id], new Set([id]));
  return [...cycles.values()];
}

/**
 * Deterministic, closed GTA-style routes over the existing road network.
 *
 * Every highway link gets a two-way mixed route with boulevard excursions at
 * both hubs. Simple highway cycles add longer inter-city journeys, and every
 * country gets full +/-span X and Z boulevard loops. All direction changes are
 * tangent-continuous; highway lanes are right-hand offset and hub transitions
 * remain inside the round asphalt. Invalid/duplicate links are ignored.
 */
export function createOpenWorldRoutes(
  anchors: Readonly<Record<string, OpenWorldAnchor>>,
  highwayLinks: readonly OpenWorldHighwayLink[],
  options: OpenWorldRouteOptions = {}
): TrafficPath[] {
  const resolved = resolveRouteOptions(options);
  const normalized = normalizeAnchors(anchors, resolved);
  const byId = new Map(normalized.map((anchor) => [anchor.id, anchor]));
  const links = normalizeHighwayLinks(highwayLinks, new Set(byId.keys()));
  const routes: TrafficPath[] = [];

  links.forEach(([fromId, toId], routeIndex) => {
    const from = byId.get(fromId)!;
    const to = byId.get(toId)!;
    const forward = directionBetween(from, to);
    const backward = { x: -forward.x, z: -forward.z };
    routes.push(buildHubRoute([from, to], [forward, backward], routeIndex, resolved, true));
  });

  const cycles = findHighwayCycles([...byId.keys()], links);
  cycles.forEach((cycle, cycleIndex) => {
    const routeAnchors = cycle.map((id) => byId.get(id)!);
    const directions = routeAnchors.map((anchor, index) =>
      directionBetween(anchor, routeAnchors[(index + 1) % routeAnchors.length])
    );
    routes.push(buildHubRoute(routeAnchors, directions, links.length + cycleIndex, resolved, false));
  });

  normalized.forEach((anchor) => {
    routes.push(buildBoulevardLoop(anchor, "x", resolved));
    routes.push(buildBoulevardLoop(anchor, "z", resolved));
  });
  return routes;
}

interface RoadRectangle {
  kind: "rectangle";
  origin: TrafficPoint;
  u: Direction;
  v: Direction;
  uMin: number;
  uMax: number;
  vMin: number;
  vMax: number;
}

interface RoadDisk {
  kind: "disk";
  center: TrafficPoint;
  radius: number;
}

type RoadPrimitive = RoadRectangle | RoadDisk;

function openWorldRoadPrimitives(
  anchors: readonly RouteAnchor[],
  links: readonly (readonly [string, string])[],
  options: ResolvedRouteOptions
): RoadPrimitive[] {
  const byId = new Map(anchors.map((anchor) => [anchor.id, anchor]));
  const primitives: RoadPrimitive[] = anchors.map((anchor) => ({
    kind: "disk", center: anchor, radius: anchor.hubRadius,
  }));
  for (const anchor of anchors) {
    for (const axis of ["x", "z"] as const) {
      primitives.push({
        kind: "rectangle",
        origin: anchor,
        u: axis === "x" ? { x: 1, z: 0 } : { x: 0, z: 1 },
        v: axis === "x" ? { x: 0, z: 1 } : { x: 1, z: 0 },
        uMin: -options.boulevardHalfLength,
        uMax: options.boulevardHalfLength,
        vMin: -options.boulevardHalfWidth,
        vMax: options.boulevardHalfWidth,
      });
    }
  }
  for (const [fromId, toId] of links) {
    const from = byId.get(fromId);
    const to = byId.get(toId);
    if (!from || !to) continue;
    const direction = directionBetween(from, to);
    const length = Math.hypot(to.x - from.x, to.z - from.z);
    primitives.push({
      kind: "rectangle",
      origin: from,
      u: direction,
      v: rightNormal(direction),
      uMin: 0,
      uMax: length,
      vMin: -options.highwayHalfWidth,
      vMax: options.highwayHalfWidth,
    });
  }
  return primitives;
}

function clipAxis(
  start: number,
  delta: number,
  min: number,
  max: number,
  interval: [number, number],
  epsilon: number
): [number, number] | null {
  if (Math.abs(delta) < epsilon) {
    return start >= min - epsilon && start <= max + epsilon ? interval : null;
  }
  const a = (min - start) / delta;
  const b = (max - start) / delta;
  const lower = Math.max(interval[0], Math.min(a, b));
  const upper = Math.min(interval[1], Math.max(a, b));
  return lower <= upper ? [lower, upper] : null;
}

function rectangleSegmentInterval(
  start: TrafficPoint,
  end: TrafficPoint,
  rectangle: RoadRectangle,
  epsilon: number
): [number, number] | null {
  const dx = end.x - start.x;
  const dz = end.z - start.z;
  const relativeX = start.x - rectangle.origin.x;
  const relativeZ = start.z - rectangle.origin.z;
  let interval: [number, number] | null = clipAxis(
    relativeX * rectangle.u.x + relativeZ * rectangle.u.z,
    dx * rectangle.u.x + dz * rectangle.u.z,
    rectangle.uMin, rectangle.uMax, [0, 1], epsilon
  );
  if (!interval) return null;
  interval = clipAxis(
    relativeX * rectangle.v.x + relativeZ * rectangle.v.z,
    dx * rectangle.v.x + dz * rectangle.v.z,
    rectangle.vMin, rectangle.vMax, interval, epsilon
  );
  return interval;
}

function diskSegmentInterval(
  start: TrafficPoint,
  end: TrafficPoint,
  disk: RoadDisk,
  epsilon: number
): [number, number] | null {
  const fx = start.x - disk.center.x;
  const fz = start.z - disk.center.z;
  const dx = end.x - start.x;
  const dz = end.z - start.z;
  const radius = disk.radius + epsilon;
  const a = dx * dx + dz * dz;
  const b = 2 * (fx * dx + fz * dz);
  const c = fx * fx + fz * fz - radius * radius;
  if (a < epsilon * epsilon) return c <= epsilon ? [0, 1] : null;
  const discriminant = b * b - 4 * a * c;
  const scale = Math.max(1, b * b, Math.abs(4 * a * c));
  if (discriminant < -epsilon * scale) return null;
  const root = Math.sqrt(Math.max(0, discriminant));
  const lower = Math.max(0, (-b - root) / (2 * a));
  const upper = Math.min(1, (-b + root) / (2 * a));
  return lower <= upper ? [lower, upper] : null;
}

/** Exact coverage of a line segment by a finite union of convex road shapes. */
function segmentIsOnRoad(
  start: TrafficPoint,
  end: TrafficPoint,
  primitives: readonly RoadPrimitive[],
  epsilon: number
): boolean {
  const intervals: Array<[number, number]> = [];
  for (const primitive of primitives) {
    const interval = primitive.kind === "disk"
      ? diskSegmentInterval(start, end, primitive, epsilon)
      : rectangleSegmentInterval(start, end, primitive, epsilon);
    if (interval) intervals.push(interval);
  }
  intervals.sort((a, b) => a[0] - b[0]);
  let coveredUntil = 0;
  for (const [lower, upper] of intervals) {
    if (lower > coveredUntil + epsilon) return false;
    coveredUntil = Math.max(coveredUntil, upper);
    if (coveredUntil >= 1 - epsilon) return true;
  }
  return false;
}

export interface OpenWorldValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Checks closure, arc-length integrity, finite wrapped samples, and containment
 * of every complete segment (including the closing segment) in the road union.
 */
export function validateOpenWorldRoutes(
  routes: readonly TrafficPath[],
  anchors: Readonly<Record<string, OpenWorldAnchor>>,
  highwayLinks: readonly OpenWorldHighwayLink[],
  options: OpenWorldRouteOptions = {}
): OpenWorldValidationResult {
  const resolved = resolveRouteOptions(options);
  const normalized = normalizeAnchors(anchors, resolved);
  const links = normalizeHighwayLinks(highwayLinks, new Set(normalized.map((anchor) => anchor.id)));
  const primitives = openWorldRoadPrimitives(normalized, links, resolved);
  const errors: string[] = [];
  const epsilon = 1e-7;
  const addError = (message: string) => {
    if (errors.length < 100) errors.push(message);
  };

  if (routes.length === 0) addError("No routes to validate.");
  routes.forEach((path, routeIndex) => {
    const label = `Route ${routeIndex}`;
    if (path.points.length < 3) addError(`${label}: fewer than three points.`);
    const first = path.points[0];
    const last = path.points[path.points.length - 1];
    if (!first || !last || Math.hypot(last.x - first.x, last.z - first.z) > epsilon) {
      addError(`${label}: not closed.`);
    }
    if (!Number.isFinite(path.total) || path.total <= 0) addError(`${label}: invalid total length.`);
    if (path.cumulative.length !== path.points.length) addError(`${label}: cumulative length mismatch.`);

    let measuredTotal = 0;
    path.points.forEach((point, pointIndex) => {
      if (!Number.isFinite(point.x) || !Number.isFinite(point.z)) {
        addError(`${label}: non-finite point ${pointIndex}.`);
        return;
      }
      if (pointIndex === 0) return;
      const previous = path.points[pointIndex - 1];
      const length = Math.hypot(point.x - previous.x, point.z - previous.z);
      measuredTotal += length;
      if (!Number.isFinite(path.cumulative[pointIndex])
        || Math.abs(path.cumulative[pointIndex] - measuredTotal) > epsilon * Math.max(1, measuredTotal)) {
        addError(`${label}: invalid cumulative length at point ${pointIndex}.`);
      }
      if (!segmentIsOnRoad(previous, point, primitives, epsilon)) {
        addError(`${label}: segment ${pointIndex - 1} leaves the road network.`);
      }
    });
    if (Math.abs(path.total - measuredTotal) > epsilon * Math.max(1, measuredTotal)) {
      addError(`${label}: total does not match its points.`);
    }
    for (let sampleIndex = 0; sampleIndex <= 128; sampleIndex += 1) {
      const sample = sampleTrafficPath(path, path.total * sampleIndex / 128);
      if (![sample.x, sample.z, sample.yaw].every(Number.isFinite)) {
        addError(`${label}: non-finite sample ${sampleIndex}.`);
        break;
      }
    }
  });
  return { valid: errors.length === 0, errors };
}
