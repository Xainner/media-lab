import { AdvancedRenderer } from './studio/components/AdvancedOptions'
import Advanced from './Advanced'
import Confirm from './Confirm'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, AudioLines, Clapperboard, Compass, Contact, Film, FolderHeart, ImagePlus, Images, ListChecks, Mail, PlugZap, ScrollText, Settings2, Shield, SlidersHorizontal, Sparkles, UserRound, Users, WandSparkles, Workflow, type LucideIcon } from 'lucide-react'
import AgentView from './studio/views/AgentView'
import CreateView from './studio/views/CreateView'
import EditView, { type EditHandoff } from './studio/views/EditView'
import VideoView from './studio/views/VideoView'
import MusicView from './studio/views/MusicView'
import DirectorView from './studio/views/DirectorView'
import type { ArtifactRef } from './studio/lib/api'
import Account from './system'
import Admin from './admin'
import Providers from './Providers'
import Mcp from './Mcp'
import Lab, { type MenuGroup } from './lab/Lab'
import { api } from './bridge'
import { Empty, Modal, PageHeading } from './ui'

type Nav = { path: string; title: string; icon: LucideIcon; tone: string; hint?: string }
const creative: Nav[] = [ {path:'/',title:'Explorar',icon:Compass,tone:'image',hint:'Inicio'}, {path:'/image',title:'Imagen',icon:ImagePlus,tone:'image',hint:'Qwen Image 2.1'}, {path:'/video',title:'Vídeo',icon:Film,tone:'video',hint:'MiniMax H3'}, {path:'/audio',title:'Audio',icon:AudioLines,tone:'music',hint:'YuE2 3B'}, {path:'/director',title:'Director',icon:Clapperboard,tone:'director',hint:'Videoclips'} ]
const advanced: Nav[] = [ {path:'/advanced/image',title:'Imagen avanzada',icon:ImagePlus,tone:'image',hint:'Semilla, precisión, comparar'}, {path:'/edit',title:'Edición avanzada',icon:WandSparkles,tone:'edit',hint:'Hasta 10 referencias'}, {path:'/advanced/video',title:'Vídeo avanzado',icon:Film,tone:'video',hint:'Fotogramas, audio y escalado'}, {path:'/advanced/music',title:'Música avanzada',icon:AudioLines,tone:'music',hint:'Partitura, pasos y semilla'}, {path:'/advanced/director',title:'Director avanzado',icon:Clapperboard,tone:'director',hint:'Precisión, pasos, reutilizar clips'}, {path:'/agent',title:'Agente',icon:Sparkles,tone:'agent',hint:'Encadena herramientas con tu proveedor IA'} ]
const library: Nav[] = [{path:'/library',title:'Biblioteca',icon:FolderHeart,tone:'library'},{path:'/gallery',title:'Galería',icon:Images,tone:'library',hint:'Solo imágenes'},{path:'/characters',title:'Personajes',icon:Contact,tone:'library',hint:'@personajes y LoRAs'},{path:'/jobs',title:'Mis trabajos',icon:ListChecks,tone:'library'}]
const account: Nav[] = [{path:'/account/profile',title:'Mi perfil',icon:UserRound,tone:'account'},{path:'/account/providers',title:'Proveedores IA',icon:Workflow,tone:'account'},{path:'/account/mcp',title:'Conexiones MCP',icon:PlugZap,tone:'account'},{path:'/account/preferences',title:'Preferencias',icon:SlidersHorizontal,tone:'account'},{path:'/account/security',title:'Seguridad',icon:Shield,tone:'account'}]
const administration: Nav[] = [{path:'/admin/users',title:'Usuarios',icon:Users,tone:'account'},{path:'/admin/invitations',title:'Invitaciones',icon:Mail,tone:'account'},{path:'/admin/providers',title:'Proveedores aprobados',icon:Workflow,tone:'account'},{path:'/admin/mail',title:'Correo y entregas',icon:Mail,tone:'account'},{path:'/admin/audit',title:'Auditoría',icon:ScrollText,tone:'account'},{path:'/admin/system',title:'Estado del sistema',icon:Settings2,tone:'account'}]

export default function Studio({ current, refresh, logout }: { current: any; refresh: () => Promise<void>; logout: () => Promise<void> }) {
 const location = useLocation(), navigate = useNavigate()
 const path = location.pathname
 const groups = useMemo(() => [['Estudio',creative],['Modo avanzado',advanced],['Tu espacio',library],['Cuenta',account],...(current.role === 'admin' ? [['Administración',administration]] : [])] as [string,Nav[]][], [current.role])
 const nav = groups.flatMap(g => g[1])
 const page = nav.find(n => n.path === path)
 const menu: MenuGroup[] = groups.filter(([label]) => label !== 'Estudio').map(([label,items]) => ({ label, items: items.map(({path,title}) => ({path,title})) }))
 const [visited,setVisited] = useState(new Set([path]))
 const [health,setHealth] = useState<any>(null)
 const [command,setCommand] = useState(false)
 const [search,setSearch] = useState('')
 const [edit,setEdit] = useState<EditHandoff|null>(null)
 const [video,setVideo] = useState<ArtifactRef|null>(null)
 const tone = page?.tone || 'image'
 useEffect(() => { setVisited(v => new Set([...v,path])) }, [path])
 useEffect(() => { let live = true; const load = () => void api('GET','/v1/health').then(v => {if(live) setHealth(v)}).catch(() => {if(live) setHealth(null)}); load(); const timer=setInterval(load,8000); return () => {live=false;clearInterval(timer)} }, [])
 useEffect(() => { const key = (e: KeyboardEvent) => { if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {e.preventDefault();setCommand(v=>!v)} }; window.addEventListener('keydown',key); return () => window.removeEventListener('keydown',key) }, [])
 const mounted = (p:string) => visited.has(p) || path===p
 const results = nav.filter(n=>n.title.toLowerCase().includes(search.toLowerCase()) || n.hint?.toLowerCase().includes(search.toLowerCase()))
 // Classic tools stay mounted once visited so a running job keeps its state while the user browses.
 const classic = <>
  {mounted('/agent') && <section hidden={path!=='/agent'} className="tool-screen" data-tone="agent"><PageHeading eyebrow="Modo avanzado · Agente" title="Pide. El agente lo encadena." plate="home">Un mensaje y tu proveedor IA usa las herramientas del Lab en varios pasos: imagen, edición, vídeo, música y videoclips.</PageHeading><Providers compact/><AgentView active={path==='/agent'}/></section>}
  {mounted('/advanced/image') && <section hidden={path!=='/advanced/image'} className="tool-screen" data-tone="image"><PageHeading eyebrow="Modo avanzado · Qwen Image 2.1" title="Control total de la imagen." plate="image"/><CreateView active={path==='/advanced/image'}/></section>}
  {mounted('/edit') && <section hidden={path!=='/edit'} className="tool-screen" data-tone="edit"><PageHeading eyebrow="Modo avanzado · Edición" title="Dale una nueva mirada." plate="edit"/><EditView active={path==='/edit'} incoming={edit}/></section>}
  {mounted('/advanced/video') && <section hidden={path!=='/advanced/video'} className="tool-screen" data-tone="video"><PageHeading eyebrow="Modo avanzado · MiniMax H3" title="Tus ideas, en movimiento." plate="video"/><VideoView incoming={video}/></section>}
  {mounted('/advanced/music') && <section hidden={path!=='/advanced/music'} className="tool-screen" data-tone="music"><PageHeading eyebrow="Modo avanzado · YuE2" title="Encuentra tu próximo sonido." plate="music"/><MusicView/></section>}
  {mounted('/advanced/director') && <section hidden={path!=='/advanced/director'} className="tool-screen" data-tone="director"><PageHeading eyebrow="Modo avanzado · Director" title="Una canción. Toda una historia." plate="director"/><DirectorView/></section>}
  {path==='/account/mcp' && <Mcp current={current}/>}
  {path==='/account/providers' && <><PageHeading eyebrow="Conecta tu inteligencia" title="Proveedores IA">Tus claves, tus modelos, tu forma de crear.</PageHeading><Providers/></>}
  {['/account/profile','/account/security','/account/preferences'].includes(path) && <Account key={path} section={path.split('/').at(-1)!} current={current} refresh={refresh}/>}
  {path.startsWith('/admin/') && current.role==='admin' && page && <Admin key={path} section={path.split('/').at(-1)!} current={current} refresh={refresh} health={health}/>}
  {!page && <Empty title="Esta página no existe" pose="sleep"><Link to="/">Volver a explorar</Link></Empty>}
 </>
 return <AdvancedRenderer.Provider value={Advanced}>
  <Lab current={current} health={health} groups={menu} onLogout={() => void logout()} classic={classic} tone={tone}/>
  <Modal open={command} onOpenChange={setCommand} title="¿A dónde vamos?" description="Busca una herramienta o una pantalla de tu espacio."><input autoFocus aria-label="Buscar pantalla" placeholder="Imagen, vídeo, usuarios, proveedores…" value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{ if(e.key==='Enter' && results[0]) { navigate(results[0].path); setCommand(false); setSearch('') } }}/><div className="command-results">{results.map(n=><button key={n.path} data-tone={n.tone} onClick={()=>{navigate(n.path);setCommand(false);setSearch('')}}><n.icon size={18}/><span>{n.title}{n.hint && <small>{n.hint}</small>}</span><ArrowRight size={16}/></button>)}</div></Modal>
  <Confirm/>
 </AdvancedRenderer.Provider>
}
