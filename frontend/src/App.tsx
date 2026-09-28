import {useEffect,useState} from 'react'
import {Dashboard} from './pages/Dashboard'
import {ReviewDetails} from './pages/ReviewDetails'
import './App.css'
export default function App() {
 const [hash,setHash]=useState(window.location.hash)
 useEffect(()=>{const update=()=>setHash(window.location.hash);window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update)},[])
 const match=hash.match(/^#\/reviews\/([0-9a-f-]+)$/i)
 return <><header><a href="#/" className="brand"><span className="brand-icon">D</span>DevFlow <strong>AI</strong></a><span className="local">LOCAL DEVELOPMENT</span></header><main>{match ? <ReviewDetails key={match[1]} id={match[1]}/> : <Dashboard/>}</main><footer>DevFlow AI ? Findings are advisory. Review suggestions before applying them.</footer></>
}
