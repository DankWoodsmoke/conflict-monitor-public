/** Inherited reference geometry. Original sources, survey dates and positional accuracy are unverified. Never an operational observation. */
export const CHOKEPOINTS = [
  { name: "Strait of Hormuz", lat: 26.60, lng: 56.50, critical: true  },
  { name: "Bab el-Mandeb",    lat: 12.60, lng: 43.40, critical: true  },
  { name: "Suez Canal",       lat: 30.45, lng: 32.35, critical: true  },
  { name: "Turkish Straits",  lat: 41.12, lng: 29.08, critical: false },
];

export const BASES = [
  { name: "Al Udeid AB (USAF/Qatar)",    lat: 25.12, lng: 51.32, col: "#58a6ff" },
  { name: "Al Dhafra AB (USAF/UAE)",     lat: 24.25, lng: 54.55, col: "#58a6ff" },
  { name: "Camp Lemonnier (USAF/DJ)",    lat: 11.55, lng: 43.16, col: "#58a6ff" },
  { name: "Ali Al Salem AB (USAF/KW)",   lat: 29.34, lng: 47.52, col: "#58a6ff" },
  { name: "Diego Garcia (USAF)",         lat: -7.31, lng: 72.41, col: "#58a6ff" },
  { name: "Incirlik AB (NATO/TR)",       lat: 37.00, lng: 35.43, col: "#9b59b6" },
  { name: "Muwaffaq Salti AB (JO)",      lat: 32.36, lng: 36.26, col: "#9b59b6" },
  { name: "Nevatim AB (IDF)",            lat: 31.21, lng: 35.01, col: "#3fb950" },
  { name: "Palmachim AB (IDF)",          lat: 31.90, lng: 34.69, col: "#3fb950" },
  { name: "Fordow Enrichment (Iran)",    lat: 34.8834, lng: 50.2278, col: "#f85149" },
  { name: "Natanz Enrichment (Iran)",    lat: 33.72, lng: 51.73, col: "#f85149" },
  { name: "Bushehr Nuclear (Iran)",      lat: 28.83, lng: 50.89, col: "#f85149" },
  { name: "Isfahan Military (Iran)",     lat: 32.65, lng: 51.67, col: "#d43030" },
  { name: "Khmeimim AB (Russia/Syria)",  lat: 35.40, lng: 35.95, col: "#d29922" },
  { name: "Al Minhad AB (UAE)",          lat: 25.03, lng: 55.37, col: "#9b59b6" },
  { name: "Prince Sultan AB (SA)",       lat: 24.06, lng: 47.58, col: "#58a6ff" },
  { name: "Mina Salman NB (Bahrain)",    lat: 26.20, lng: 50.60, col: "#58a6ff" },
];

// Key oil refineries
export const REFINERIES = [
  { name: "Ras Tanura Refinery (SA)",     lat: 26.65, lng: 50.17 },
  { name: "Abadan Refinery (Iran)",       lat: 30.34, lng: 48.28 },
  { name: "Bandar Abbas Refinery (Iran)", lat: 27.22, lng: 56.25 },
  { name: "Tehran Refinery (Iran)",       lat: 35.63, lng: 51.33 },
  { name: "Haifa Refinery (Israel)",      lat: 32.82, lng: 35.04 },
  { name: "Jubail Refinery (SA)",         lat: 27.01, lng: 49.62 },
  { name: "Kuwait KNPC Mina Abdullah",    lat: 29.04, lng: 48.08 },
  { name: "Ruwais Refinery (UAE)",        lat: 24.11, lng: 52.73 },
  { name: "Erbil Refinery (Iraq)",        lat: 36.19, lng: 43.99 },
  { name: "Baiji Refinery (Iraq)",        lat: 34.94, lng: 43.49 },
];

// Key airfields (strategic/military — bases already listed separately)
export const AIRFIELDS = [
  { name: "Mehrabad Airport (Iran-military)", lat: 35.69, lng: 51.31 },
  { name: "Shahid Nojeh AB (Iran)",           lat: 35.21, lng: 48.65 },
  { name: "Dezful AB (Iran)",                 lat: 32.43, lng: 48.40 },
  { name: "Tabriz AB (Iran)",                 lat: 38.13, lng: 46.24 },
  { name: "Mashhad AB (Iran)",                lat: 36.24, lng: 59.64 },
  { name: "King Khalid Mil City (SA)",        lat: 27.90, lng: 45.52 },
  { name: "Aleppo Airbase (Syria)",           lat: 36.18, lng: 37.22 },
  { name: "H4 Airbase (Jordan)",              lat: 33.19, lng: 38.20 },
  { name: "Tiyas AB T4 (Syria)",              lat: 34.52, lng: 37.62 },
  { name: "Deir ez-Zor Airport (Syria)",      lat: 35.29, lng: 40.18 },
  { name: "Ramat David AB (Israel)",          lat: 32.67, lng: 35.18 },
  { name: "Ramon AB (Israel)",                lat: 29.73, lng: 34.95 },
];

// Key pipeline segments (simplified lat/lon waypoints)
export const OIL_PIPELINES: { name: string; points: [number, number][] }[] = [
  {
    name: "Baku–Tbilisi–Ceyhan (BTC)",
    points: [[40.38,49.85],[41.70,45.35],[41.00,41.50],[36.80,36.10]],
  },
  {
    name: "Iraq–Turkey Pipeline (Kirkuk–Ceyhan)",
    points: [[35.47,44.39],[37.10,42.50],[37.55,37.00],[36.80,36.10]],
  },
  {
    name: "Saudi East–West Pipeline (Petroline)",
    points: [[26.31,49.98],[24.68,46.72],[23.50,43.00],[23.00,38.50]],
  },
  {
    name: "IGAT Gas Pipeline (Iran)",
    points: [[27.18,56.27],[30.15,50.50],[33.00,48.50],[35.50,46.00]],
  },
  {
    name: "Arab Gas Pipeline",
    points: [[30.00,32.30],[30.09,32.42],[31.20,34.79],[32.20,34.98]],
  },
];

export const GAS_PIPELINES: { name: string; points: [number, number][] }[] = [
  {
    name: "South Pars/North Dome Gas Field Pipeline",
    points: [[27.50,51.00],[27.00,50.50],[26.65,50.17]],
  },
  {
    name: "Iran–Turkey Gas Pipeline",
    points: [[38.08,46.30],[38.50,44.00],[39.90,41.10],[39.92,40.75]],
  },
  {
    name: "Dolphin Gas Pipeline (Qatar–UAE–Oman)",
    points: [[25.58,51.53],[24.50,53.50],[23.59,58.59]],
  },
];

