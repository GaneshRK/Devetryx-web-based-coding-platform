// Minimal JS for interactivity
document.addEventListener('DOMContentLoaded', function(){
  const navToggle = document.getElementById('nav-toggle');
  const navMenu = document.getElementById('nav-menu');
  if(navToggle){
    navToggle.addEventListener('click', function(){
      const expanded = this.getAttribute('aria-expanded') === 'true';
      this.setAttribute('aria-expanded', !expanded);
      navMenu.style.display = expanded ? 'none' : 'flex';
    });
  }
  const loadBtn = document.getElementById('load-more');
  if(loadBtn){
    loadBtn.addEventListener('click', async function(){
      const container = document.getElementById('features-list');
      const more = [
        {icon:'⚡', title:'Low-latency', subtitle:'Fast inference pipeline'},
        {icon:'🔒', title:'Private by design', subtitle:'On-device models available'},
      ];
      more.forEach(m=>{
        const article = document.createElement('article');
        article.className='card';
        article.innerHTML = `<div class="card-icon">${m.icon}</div><div><h3>${m.title}</h3><p class="muted">${m.subtitle}</p></div>`;
        container.appendChild(article);
      });
      this.textContent = 'Loaded';
      this.disabled = true;
    });
  }
  const form = document.getElementById('contact-form');
  if(form){
    form.addEventListener('submit', async function(e){
      e.preventDefault();
      const status = document.getElementById('contact-status');
      status.textContent = 'Sending...';
      const data = new FormData(form);
      try{
        const resp = await fetch(form.action, {
          method:'POST',
          body: data,
          headers: {'X-Requested-With':'XMLHttpRequest'}
        });
        const json = await resp.json();
        if(json.status === 'success'){
          status.textContent = json.message;
          form.reset();
        } else {
          status.textContent = json.message || 'Error';
        }
      } catch(err){
        status.textContent = 'Network error';
      }
    });
  }
});
