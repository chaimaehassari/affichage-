const STORAGE_KEY = 'dyndisplay_device_id';

function generateDeviceId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return 'dev-' + window.crypto.randomUUID();
  }
  const values = new Uint32Array(3);
  if (window.crypto && typeof window.crypto.getRandomValues === 'function') {
    window.crypto.getRandomValues(values);
    return (
      'dev-' +
      values[0].toString(36) +
      values[1].toString(36) +
      values[2].toString(36) +
      '-' +
      Date.now().toString(36).slice(-6)
    );
  }
  return 'dev-' + Math.random().toString(36).slice(2) + '-' + Date.now().toString(36);
}

export function getDeviceId() {
  let deviceId = null;
  try {
    deviceId = window.localStorage.getItem(STORAGE_KEY);
  } catch (e) {
    deviceId = null;
  }
  if (!deviceId) {
    deviceId = generateDeviceId();
    try {
      window.localStorage.setItem(STORAGE_KEY, deviceId);
    } catch (e) {
      // localStorage indisponible : on garde un id de session.
    }
  }
  return deviceId;
}