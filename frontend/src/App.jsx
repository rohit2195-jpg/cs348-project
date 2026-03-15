// App.jsx — Root entry point. Wraps everything in ThemeProvider.
// All dashboard logic lives in components/Dashboard.jsx
import { ThemeProvider } from './Settings';
import Dashboard from './components/Dashboard';

export default function App() {
  return (
    <ThemeProvider>
      <Dashboard />
    </ThemeProvider>
  );
}