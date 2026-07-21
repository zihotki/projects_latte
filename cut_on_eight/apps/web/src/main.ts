import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

const target = document.querySelector<HTMLDivElement>('#app');

if (!target) {
  throw new Error('Application root was not found');
}

mount(App, { target });
