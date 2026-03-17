import React from 'react';

const App: React.FC = () => {
  return (
    <div style={{ textAlign: 'center', padding: '50px', fontFamily: 'sans-serif' }}>
      <h1>DWRS Portal</h1>
      <p>The Domestic Worker Registration & Verification System frontend is running successfully!</p>
      <p>Local API Endpoints to consume:</p>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        <li>Auth: port 8001</li>
        <li>Registration: port 8002</li>
        <li>Verification: port 8003</li>
        <li>Risk Scoring: port 8004</li>
        <li>Audit: port 8005</li>
      </ul>
    </div>
  );
};

export default App;
