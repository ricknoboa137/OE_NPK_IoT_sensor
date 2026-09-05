// Shared config for the tool scripts in this folder.
// sqlite3 is installed as a dependency of Node-RED's sqlite node, not here.
const path = require('path');

const NODE_RED_MODULES = path.join(
    process.env.USERPROFILE, '.node-red', 'node_modules', 'sqlite3');

module.exports = {
    sqlite3: require(NODE_RED_MODULES),
    DB: path.join(__dirname, '..', 'DB_01.db'),
    OLD_DB: path.join(__dirname, '..', 'original', 'DB_01_original_ms.db'),
};
