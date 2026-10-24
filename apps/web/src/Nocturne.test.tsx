import {afterEach,beforeEach,expect,test,vi} from 'vitest'
import {act,cleanup,render,screen} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {MemoryRouter} from 'react-router-dom'
import Entry from './entry/Entry'
import Studio from './Studio'
import {JOB_EVENT} from './studio/lib/api'
vi.mock('./bridge',()=>({api:async(_method:string,route:string)=>route==='/v1/health'?{status:'ok'}:{items:[]}}))

const media=(reduce:boolean)=>vi.stubGlobal('matchMedia',(q:string)=>({matches:reduce&&q.includes('reduce'),addEventListener(){},removeEventListener(){}}))
beforeEach(()=>{
 vi.stubGlobal('ResizeObserver',class{observe(){} unobserve(){} disconnect(){}})
 window.scrollTo=()=>{}
 window.visualLab={platform:'web',runtime:{request:async()=>({})}} as any
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear();sessionStorage.clear();vi.useRealTimers()})

const entry=()=>render(<Entry mode="login" loading={false} factor={null} mood="idle" say=""><button>ENTRAR</button></Entry>)

test('the cinematic intro plays once, can be skipped and remembers it for the session',async()=>{
 media(false)
 const user=userEvent.setup()
 entry()
 expect(screen.getByRole('button',{name:'Saltar intro'})).toBeTruthy()
 await user.click(screen.getByRole('button',{name:'Saltar intro'}))
 expect(screen.queryByRole('button',{name:'Saltar intro'})).toBeNull()
 expect(sessionStorage.getItem('rvl-intro-seen')).toBe('1')
 cleanup();entry()
 expect(screen.queryByRole('button',{name:'Saltar intro'})).toBeNull()
 expect(screen.getByRole('button',{name:'ENTRAR'})).toBeTruthy()
})

test('the intro is absent with reduced motion or with studio animation turned off',()=>{
 media(true);entry()
 expect(screen.queryByRole('button',{name:'Saltar intro'})).toBeNull()
 cleanup();media(false);localStorage.setItem('media-lab:animation-mode','off');entry()
 expect(screen.queryByRole('button',{name:'Saltar intro'})).toBeNull()
})

const studio=(role:string,path='/')=>render(<MemoryRouter initialEntries={[path]} future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Studio current={{username:'rinari',user_id:'one',role}} refresh={async()=>{}} logout={async()=>{}}/></MemoryRouter>)

test('the account menu exposes administration only to admins and the command palette navigates',async()=>{
 media(true)
 const user=userEvent.setup()
 studio('admin','/advanced/image')
 await user.click(screen.getByRole('button',{name:'Menú de la cuenta'}))
 expect(screen.getByRole('link',{name:'Usuarios',exact:true})).toBeTruthy()
 await user.keyboard('{Escape}')
 await user.keyboard('{Control>}k{/Control}')
 const search=await screen.findByLabelText('Buscar pantalla')
 await user.type(search,'música')
 await user.keyboard('{Enter}')
 expect(await screen.findByRole('heading',{name:'Encuentra tu próximo sonido.'})).toBeTruthy()
})
