const loadBtn = document.getElementById('load-btn');
const result = document.getElementById('result');

loadBtn?.addEventListener('click', async () => {
  const learner = document.getElementById('learner').value.trim();
  const note = document.getElementById('note').value.trim();

  const res = await fetch('/api/daily', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ learner_id: learner, note }),
  });

  const data = await res.json();
  result.classList.remove('hidden');

  const activities = data?.content?.activities || [];
  result.innerHTML = `
    <h2>Dificultad ${data.difficulty}/10</h2>
    <p><strong>Juegos de hoy:</strong> ${data.games.join(', ')}</p>
    <h3>Actividades sugeridas</h3>
    <ul>${activities.map((a) => `<li>${a.game}: ${a.prompt}</li>`).join('')}</ul>
  `;
});
