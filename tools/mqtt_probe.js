// Listen to the node's topics and optionally send one read-only command.
//   node tools/mqtt_probe.js            just listen for 20 s
//   node tools/mqtt_probe.js cal_list   also ask for the coefficient table
//
// cal_list only reads NVS. Nothing here writes calibration.
const path = require('path');
// mqtt ships inside Node-RED itself, not in the user directory
const mqtt = require(path.join(process.env.APPDATA, 'npm', 'node_modules',
                               'node-red', 'node_modules', 'mqtt'));

const HOST = 'mqtt://192.168.0.153:1883';
const SEND = process.argv[2] === 'cal_list';
const WINDOW_MS = 20000;

const client = mqtt.connect(HOST, { connectTimeout: 8000 });

client.on('connect', () => {
    console.log('connected to ' + HOST);
    client.subscribe(['NPKdata', 'NPKstatus', 'NPKreply'], (e) => {
        if (e) { console.log('subscribe error: ' + e.message); process.exit(1); }
        console.log('subscribed: NPKdata, NPKstatus, NPKreply\n');
        if (SEND) {
            const cmd = JSON.stringify({ cmd: 'cal_list' });
            client.publish('NPKcommand', cmd);
            console.log('-> NPKcommand ' + cmd + '\n');
        }
    });
});

client.on('error', (e) => { console.log('mqtt error: ' + e.message); process.exit(1); });

let data = 0;
client.on('message', (topic, buf) => {
    const s = buf.toString();
    if (topic === 'NPKdata') {
        data++;
        if (data <= 2) {
            let keys = '';
            try { keys = ' keys: ' + Object.keys(JSON.parse(s)).join(','); } catch (e) {}
            console.log('<- NPKdata ' + s + keys);
        }
        return;
    }
    console.log('<- ' + topic + ' ' + JSON.stringify(s));
});

setTimeout(() => {
    console.log('\n' + data + ' NPKdata messages in ' + (WINDOW_MS / 1000) + 's');
    client.end(true, () => process.exit(0));
}, WINDOW_MS);
