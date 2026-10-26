// Task 2: MongoDB queries (run in mongosh: `mongosh beijing_air mongo/queries.js`)
// db = beijing_air, collection = readings

// Q1. Latest record
db.readings.find().sort({ timestamp: -1 }).limit(1);

// Q2. Hazardous hours (PM2.5 > 300) during winter 2013, by date range
db.readings.find(
  {
    timestamp: { $gte: ISODate("2013-01-01T00:00:00Z"), $lt: ISODate("2013-03-01T00:00:00Z") },
    "air_quality.pm25": { $gt: 300 }
  },
  { _id: 0, timestamp: 1, "air_quality.pm25": 1, "weather.temp": 1, "weather.wind.direction": 1 }
).sort({ timestamp: 1 }).limit(20);

// Q3. Average PM2.5 by wind direction ($avg ignores null values)
db.readings.aggregate([
  { $match: { "air_quality.pm25": { $ne: null } } },
  { $group: { _id: "$weather.wind.direction",
              avg_pm25: { $avg: "$air_quality.pm25" },
              n_readings: { $sum: 1 } } },
  { $project: { avg_pm25: { $round: ["$avg_pm25", 1] }, n_readings: 1 } },
  { $sort: { avg_pm25: -1 } }
]);

// Q4. Monthly average PM2.5 and temperature
db.readings.aggregate([
  { $group: { _id: { $dateToString: { format: "%Y-%m", date: "$timestamp" } },
              avg_pm25: { $avg: "$air_quality.pm25" },
              avg_temp: { $avg: "$weather.temp" },
              missing_pm25: { $sum: { $cond: [{ $eq: ["$air_quality.pm25", null] }, 1, 0] } } } },
  { $project: { avg_pm25: { $round: ["$avg_pm25", 1] },
                avg_temp: { $round: ["$avg_temp", 1] }, missing_pm25: 1 } },
  { $sort: { _id: 1 } }
]);
