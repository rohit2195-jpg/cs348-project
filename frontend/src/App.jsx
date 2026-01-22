import { useEffect, useState } from 'react'
import reactLogo from './assets/react.svg'
import viteLogo from '/vite.svg'
import './App.css'

function App() {
  const [count, setCount] = useState(0)
  const [message, setMessage] = useState('')

  async function callBackend() {
    const response = await fetch("http://127.0.0.1:5000");

    const data = await response.json(); // read once
    console.log(data);

    setMessage(data.message);
  }


  useEffect(() => {
     callBackend()

  }, [])

  return (
    <>
      <div>
        <p>This is the frontend of the app</p>

        {message ? <p> {message}</p> : <p>Not connected to backend</p>}

      </div>
    </>
  )
}

export default App
