from copy import deepcopy
from pathlib import Path
import runpy
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / 'Codigo'))
import calibracion as ajustes
import medidor_backend as b
from test_medicion_calibracion import perfil
from test_calibracion_abierto import abierto_simulado


class InterfazCalibracionTests(unittest.TestCase):
    def setUp(self):
        with patch.object(tk.Tk,'mainloop'),patch.object(ajustes,'cargar',return_value=None):
            ui=runpy.run_path(str(PROYECTO/'Codigo/Interfaz.py'))
        self.ui=ui['_iniciar_tarea'].__globals__
        self.root=self.ui['root']
        self.addCleanup(self.root.destroy)
        self.addCleanup(self.ui['plt'].close,'all')

    def entrada(self,nombre,texto):
        widget=self.ui[nombre]
        widget.delete(0,'end')
        widget.insert(0,texto)

    def esperar(self):
        limite=time.monotonic()+4
        while self.ui['_tarea_en_curso'] and time.monotonic()<limite:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.ui['_tarea_en_curso'])

    def test_campo_editable_tabla_guardado_y_activacion(self):
        self.ui['combo_r'].current(1)
        self.entrada('ent_r_cal','2200')
        self.entrada('ent_cal_fin','2000')
        self.entrada('ent_cal_pasos','2')
        esperado=perfil()
        esperado['r_referencia']=2200
        self.ui['_abierto']=abierto_simulado(100)
        def calibrar(f_ini,f_fin,pasos,rs,r_ref,progreso,abierto):
            self.assertEqual((f_ini,f_fin,pasos,rs,r_ref),(1000,2000,2,100,2200))
            for indice,p in enumerate(esperado['puntos'],1):
                progreso({'indice':indice,'total':2,'punto':p})
            return {'exito':True,'calibracion':esperado,'puntos':esperado['puntos']}
        with tempfile.TemporaryDirectory() as carpeta,patch.object(ajustes,'RUTA_CALIBRACION',Path(carpeta)/'cal.json'),patch.object(b,'calibrar_barrido',side_effect=calibrar):
            self.ui['ejecutar_calibracion']()
            self.assertTrue(self.ui['btn_actualizar_equipos'].instate(['disabled']))
            self.esperar()
            self.assertEqual(ajustes.cargar(),esperado)
        self.assertEqual(len(self.ui['tabla_cal'].get_children()),2)
        self.assertTrue(self.ui['usar_calibracion'].get())
        self.assertIn('Aplicando calibración',self.ui['lbl_calibracion_uso']['text'])

    def test_fallo_no_reemplaza_calibracion_previa(self):
        anterior=perfil()
        self.ui['_calibracion']=anterior
        with patch.object(ajustes,'guardar') as guardar,patch.object(self.ui['messagebox'],'showerror'):
            self.ui['mostrar_calibracion']({'exito':False,'error':'Punto inválido'})
        guardar.assert_not_called()
        self.assertIs(self.ui['_calibracion'],anterior)

    def test_no_inicia_resistencia_sin_abierto_o_si_cambia_el_rango(self):
        with patch.object(b,'calibrar_barrido') as calibrar,patch.object(self.ui['messagebox'],'showerror') as error:
            self.ui['ejecutar_calibracion']()
            self.assertIn('Primero',error.call_args.args[1])
            self.ui['_abierto']=abierto_simulado()
            self.ui['ejecutar_calibracion']()
            self.assertIn('mismo barrido',error.call_args.args[1])
        calibrar.assert_not_called()

    def test_abierto_se_mide_manualmente_y_no_activa_un_perfil(self):
        self.entrada('ent_cal_fin','2000');self.entrada('ent_cal_pasos','2')
        esperado=abierto_simulado()
        with patch.object(b,'medir_abierto',return_value={'exito':True,'abierto':esperado}) as medir:
            self.ui['ejecutar_abierto']()
            self.assertTrue(self.ui['btn_calibrar'].instate(['disabled']))
            self.esperar()
        self.assertEqual(medir.call_args.args,(1000,2000,2,10))
        self.assertEqual(self.ui['_abierto'],esperado)
        self.assertFalse(self.ui['usar_calibracion'].get())
        self.assertIn('Colocá la resistencia',self.ui['lbl_estado_cal']['text'])

    def test_calibracion_invalida_se_desactiva_al_cargar_sin_consultar_usb(self):
        self.ui['_calibracion'] = perfil()
        self.ui['usar_calibracion'].set(True)
        with patch.object(ajustes, 'cargar', side_effect=ValueError('Repetí la calibración')), patch.object(self.ui['instrumentos_usb'], 'detectar_instrumentos') as detectar:
            self.ui['cargar_calibracion_guardada']()
        detectar.assert_not_called()
        self.assertIsNone(self.ui['_calibracion'])
        self.assertFalse(self.ui['usar_calibracion'].get())
        self.assertIn('Repetí la calibración', self.ui['lbl_estado_cal']['text'])

    def test_reintento_muestra_frecuencia_y_no_agrega_fila_invalida(self):
        evento={'indice':1,'total':2,'frecuencia':1000,'reintento':2,'max_reintentos':3,'error':'sin señal'}
        self.ui['progreso_calibracion'](evento)
        self.assertIn('1000 Hz (2/3)',self.ui['lbl_estado_cal']['text'])
        self.assertEqual(len(self.ui['tabla_cal'].get_children()),0)
        self.ui['progreso_barrido'](evento)
        self.assertIn('1000 Hz (2/3)',self.ui['lbl_estado']['text'])

    def test_medicion_recibe_perfil_y_error_borra_resultados_anteriores(self):
        self.ui['_calibracion']=perfil()
        self.ui['usar_calibracion'].set(True)
        self.ui['combo_r'].current(1)
        self.ui['lbl_z'].config(text='100 Ω')
        with patch.object(b,'medicion_simple',return_value={'exito':False,'error':'ESR negativa'}) as medir:
            self.ui['ejecutar_medicion']()
            self.esperar()
        medir.assert_called_once_with(100,perfil())
        self.assertEqual(self.ui['lbl_z']['text'],'---')
        self.assertEqual(self.ui['lbl_tipo_final']['text'],'LECTURA INVÁLIDA')

    def test_graficos_mixtos_separan_valores_y_unidades(self):
        cap=b._procesar_matematica(0.05,0.1,1000,135,10)
        ind=b._procesar_matematica(0.05,0.1,2000,-135,10)
        res={'exito':True,'frec_medida':[1000,2000],'esr':[cap['esr_num'],ind['esr_num']],
             'por_tipo':{'CAPACITOR':[cap],'INDUCTOR':[ind],'RESISTENCIA':[]},'errores_log':[]}
        self.ui['mostrar_barrido'](res)
        plt=self.ui['plt']
        eje_c=plt.figure('Capacitancia').axes[0]
        eje_l=plt.figure('Inductancia').axes[0]
        self.assertEqual(list(eje_c.lines[0].get_xdata()),[1000])
        self.assertEqual(list(eje_l.lines[0].get_xdata()),[2000])
        self.assertIn('(F)',eje_c.get_ylabel())
        self.assertIn('(H)',eje_l.get_ylabel())
        self.assertEqual(list(eje_c.lines[0].get_ydata()),[cap['valor_num']])
        self.assertEqual(list(eje_l.lines[0].get_ydata()),[ind['valor_num']])

    def test_perfil_guardado_se_carga_sin_consultar_equipos(self):
        with patch.object(ajustes,'cargar',return_value=perfil()),patch.object(self.ui['instrumentos_usb'],'detectar_instrumentos') as detectar:
            self.ui['cargar_calibracion_guardada']()
            self.root.update()
        detectar.assert_not_called()
        self.assertEqual(len(self.ui['tabla_cal'].get_children()),2)
        self.assertFalse(self.root.tk.call('after','info'))


if __name__=='__main__':
    unittest.main()
