import {
  COUNTRY_FLAT_ANCHORS,
  assignHospitalPads,
  assignRoadsideSpots,
  assignShelterPads,
  createWorldLayout,
  generateBuildings,
  generateTrees,
  validateWorldLayout,
} from "../src/simulation/worldLayout.ts";

const world = createWorldLayout();
const repeat = createWorldLayout();
const buildings = generateBuildings(world);
const trees = generateTrees(world, buildings);
const validation = validateWorldLayout(world, buildings, trees);

const hospitalRequests = Object.entries(COUNTRY_FLAT_ANCHORS).flatMap(([countryId, anchor], countryIndex) =>
  Array.from({ length: 7 }, (_, hospitalIndex) => {
    const angle = countryIndex * 0.73 + hospitalIndex * 1.41;
    const radius = 90 + hospitalIndex * 75;
    return {
      id: `${countryId}-hospital-${hospitalIndex + 1}`,
      countryId,
      x: anchor.x + Math.cos(angle) * radius,
      z: anchor.z + Math.sin(angle) * radius,
    };
  })
);
const placements = assignHospitalPads(world, hospitalRequests);
const uniquePads = new Set([...placements.values()].map((pad) => pad.id));
const shelterRequests = hospitalRequests.map((request) => ({ ...request, id: request.id.replace("hospital", "shelter") }));
const shelterPlacements = assignShelterPads(world, shelterRequests);
const uniqueShelterPads = new Set([...shelterPlacements.values()].map((pad) => pad.id));
const overflowRequests = Array.from({ length: 9 }, (_, index) => ({
  id: `overflow-${index}`,
  countryId: "COUNTRY-03",
  x: index * 40,
  z: index * 25,
}));
const overflowPlacements = assignHospitalPads(world, overflowRequests);
const overflowUniquePads = new Set([...overflowPlacements.values()].map((pad) => pad.id));
const ambulanceRequests = Object.keys(COUNTRY_FLAT_ANCHORS).flatMap((countryId) =>
  Array.from({ length: 18 }, (_, index) => ({ id: `${countryId}-ambulance-${index}`, countryId, x: index * 20, z: index * 10 }))
);
const fireRequests = Object.keys(COUNTRY_FLAT_ANCHORS).flatMap((countryId) =>
  Array.from({ length: 8 }, (_, index) => ({ id: `${countryId}-fire-${index}`, countryId, x: index * 20, z: index * 10 }))
);
const ambulanceSpots = assignRoadsideSpots(world, ambulanceRequests, "ambulance", buildings, trees);
const fireSpots = assignRoadsideSpots(world, fireRequests, "fire", buildings, trees);
const uniqueAmbulanceSpots = new Set([...ambulanceSpots.values()].map((spot) => spot.id));
const uniqueFireSpots = new Set([...fireSpots.values()].map((spot) => spot.id));

const failures = [];
if (JSON.stringify(world) !== JSON.stringify(repeat)) failures.push("Layout generation is not deterministic.");
if (!validation.ok) failures.push(...validation.issues);
if (placements.size !== hospitalRequests.length) failures.push("Not every hospital received a pad.");
if (uniquePads.size !== placements.size) failures.push("Two hospitals were assigned the same pad.");
if (shelterPlacements.size !== shelterRequests.length || uniqueShelterPads.size !== shelterPlacements.size) failures.push("Shelter pads are missing or duplicated.");
if (overflowPlacements.size > 8 || overflowUniquePads.size !== overflowPlacements.size) failures.push("Hospital overflow silently stacked facilities.");
if (ambulanceSpots.size !== ambulanceRequests.length || uniqueAmbulanceSpots.size !== ambulanceSpots.size) failures.push("Ambulance roadside spots are missing or duplicated.");
if (fireSpots.size !== fireRequests.length || uniqueFireSpots.size !== fireSpots.size) failures.push("Fire-engine roadside spots are missing or duplicated.");
if (validation.stats.lakes < 14) failures.push("Expected at least 14 organic lakes.");
if (validation.stats.forests < 18) failures.push("Expected at least 18 forest regions.");
if (validation.stats.trees < 1500) failures.push("Expected at least 1,500 trees.");
if (validation.stats.minimumHospitalRoadClearance < 18) failures.push("Hospital road clearance is below 18 m.");
if (validation.stats.minimumShelterRoadClearance < 16) failures.push("Shelter road clearance is below 16 m.");
if (validation.stats.minimumBuildingRoadClearance < 8) failures.push("Building road clearance is below 8 m.");
if (validation.stats.trafficRoutes < 20) failures.push("Expected at least 20 closed traffic routes.");

if (failures.length > 0) {
  console.error("FAIL world layout");
  failures.slice(0, 100).forEach((failure) => console.error(`- ${failure}`));
  process.exitCode = 1;
} else {
  console.log("PASS world layout");
  console.log(JSON.stringify({
    ...validation.stats,
    hospitalsPlaced: placements.size,
    uniqueHospitalPads: uniquePads.size,
    sheltersPlaced: shelterPlacements.size,
    uniqueShelterPads: uniqueShelterPads.size,
    ambulancesParked: ambulanceSpots.size,
    fireEnginesParked: fireSpots.size,
    overflowHandledWithoutStacking: overflowUniquePads.size === overflowPlacements.size,
    deterministic: true,
  }, null, 2));
}
