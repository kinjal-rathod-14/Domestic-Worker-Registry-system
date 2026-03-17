const localtunnel = require('localtunnel');

(async () => {
  try {
    const tunnel = await localtunnel({ port: 3001 });
    console.log(`Tunnel URL: ${tunnel.url}`);

    tunnel.on('close', () => {
      console.log('Tunnel closed');
    });
  } catch (error) {
    console.error('Error opening tunnel:', error);
  }
})();
