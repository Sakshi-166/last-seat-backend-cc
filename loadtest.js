import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 100,
  iterations: 100,
  thresholds: { http_req_failed: ['rate<0.05'] },
};

export default function () {
  const payload = JSON.stringify({ user_id: `user-${__VU}-${__ITER}`, seat_number: 'A001' });
  const response = http.post('http://localhost:8000/reservations', payload, {
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `load-${__VU}-${__ITER}` },
  });
  check(response, {
    'request returned expected result': (r) => r.status === 201 || r.status === 409,
  });
  sleep(0.1);
}
