from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, call, patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Codigo'))
import medidor_backend as b
from osciloscopios import Osciloscopio, protocolo_para, validar_calibracion
from test_medicion_calibracion import perfil

TEK = 'TEKTRONIX,TBS2102B,C022681,CF:91.1CT FV:v1.32.136; FPGA:v2.20;'
UNIT = 'Uni-Trend Technologies,UTD2102,SERIEUNIT,1.0'
GEN = 'UNI-T Technologies,UTG1042X,AWGA224490002,3.14'


class TekSimulado:
    """Captura binaria cuantizada, con estados de adquisición y transferencia."""
    def __init__(self, fase=-135, truncar=False, recortar=False, fallo_opc=False):
        self.timeout, self.chunk_size = 4000, 20480
        self.valores = {'ACQuire:STATE': '1', 'ACQuire:STOPAfter': 'RUNSTOP',
            'ACQuire:MODe': 'SAMPLE', 'ACQuire:NUMAVg': '8', 'DATa:ENCdg': 'SRIBINARY', 'DATa:WIDth': '1',
            'DATa:STARt': '20', 'DATa:STOP': '20000', 'DATa:SOUrce': 'CH2',
            'MEASUrement:IMMed:TYPe': 'PHASE', 'MEASUrement:IMMed:SOUrce1': 'CH2',
            'MEASUrement:GATing': 'OFF', 'HORizontal:RECOrdlength': '20000'}
        self.originales = self.valores.copy()
        self.fase, self.truncar, self.recortar, self.fallo_opc = fase, truncar, recortar, fallo_opc
        self.comandos, self.descargas = [], []

    def write(self, comando):
        self.comandos.append(comando)
        clave, valor = comando.split(' ', 1)
        self.valores[clave] = {'ON': '1', 'OFF': '0'}.get(valor, valor) if clave == 'ACQuire:STATE' else valor

    def query(self, comando):
        self.comandos.append(comando)
        if comando == '*OPC?':
            if self.fallo_opc:
                raise TimeoutError('sin disparo')
            self.valores['ACQuire:STATE'] = '0'
            return '1'
        if comando == 'MEASUrement:IMMed:VALue?':
            if self.valores['MEASUrement:IMMed:TYPe'] == 'PK2Pk':
                return str(2 * np.sqrt(2) * (.05 if self.valores['MEASUrement:IMMed:SOUrce1'] == 'CH1' else 1))
            return '1001'
        valores = {'WFMOutpre:XINcr?': 5 / 1000 / 20000, 'WFMOutpre:XZEro?': -.001,
                   'WFMOutpre:PT_Off?': 0, 'WFMOutpre:YOFf?': 0, 'WFMOutpre:YZEro?': 0,
                   'CH2:SCAle?': 1}
        if comando == 'WFMOutpre:YMUlt?':
            return str((.05 if self.valores['DATa:SOUrce'] == 'CH1' else 1) * np.sqrt(2) / 90)
        if comando in valores:
            return str(valores[comando])
        return self.valores[comando.rstrip('?')]

    def query_binary_values(self, comando, **kwargs):
        assert self.valores['ACQuire:STATE'] == '0', 'canales sin congelar'
        assert kwargs['datatype'] == 'b', 'ancho del ADC incorrecto'
        self.descargas.append((self.valores['DATa:SOUrce'], self.valores['ACQuire:STATE']))
        t = -.001 + np.arange(20000) * 5 / 1000 / 20000
        fase = 0 if self.valores['DATa:SOUrce'] == 'CH1' else np.radians(self.fase)
        datos = np.round(90 * np.sin(2 * np.pi * 1000 * t + fase))
        if self.recortar:
            datos[0] = 127
        return datos[:-20] if self.truncar else datos


class ProtocolosTests(unittest.TestCase):
    def test_identifica_marcas_y_modelos_sin_confundir_generador(self):
        for modelo in ('TBS2072B', 'TBS2074B', 'TBS2102B', 'TBS2104B', 'TBS2202B', 'TBS2204B'):
            self.assertEqual(protocolo_para(f'tektronix,{modelo},SERIE,1'), 'tektronix_tbs2000b')
        for modelo in ('DSO', 'UTD2102'):
            self.assertEqual(protocolo_para(f'UNI-T,{modelo},SERIE,1'), 'uni_t')
        self.assertIsNone(protocolo_para(GEN))
        self.assertIsNone(protocolo_para('OTRA MARCA,DSO,SERIE,1'))
        with self.assertRaisesRegex(ValueError, 'protocolo verificado'):
            protocolo_para('TEKTRONIX,TDS2024,SERIE,1')

    def test_unit_conserva_comandos_y_orden_de_canales(self):
        recurso = MagicMock()
        recurso.query.side_effect = ['0.05', '1', '1000', '135']
        osc = Osciloscopio(recurso, UNIT, 'uni_t')
        osc.configurar()
        self.assertEqual(b._leer_medicion(osc), (0.05, 1, 1000, 135))
        self.assertEqual(recurso.query.call_args_list, [call(c) for c in (
            ':MEASure:VRMS? CHANnel1', ':MEASure:VRMS? CHANnel2',
            ':MEASure:FREQuency? CHANnel2', ':MEASure:PHASe? CHANnel2,CHANnel1')])
        recurso.write.assert_not_called()
        osc.autoset()
        recurso.write.assert_called_once_with(':AUToset')

    def test_tek_mide_una_captura_comun_y_restaura_adquisicion(self):
        recurso = TekSimulado()
        osc = Osciloscopio(recurso, TEK, 'tektronix_tbs2000b')
        osc.configurar()
        vi, vr, f, fase = b._leer_medicion(osc)
        self.assertAlmostEqual(vi, .05, delta=.0001)
        self.assertAlmostEqual(vr, 1, delta=.001)
        self.assertAlmostEqual(f, 1000, delta=.1)
        self.assertAlmostEqual(fase, -135, delta=.05)
        self.assertEqual(recurso.descargas, [('CH1', '0'), ('CH2', '0')])
        for cmd, valor in recurso.originales.items():
            self.assertEqual(recurso.valores[cmd], valor)
        self.assertEqual((recurso.timeout, recurso.chunk_size), (4000, 20480))
        self.assertLess(recurso.comandos.index('*OPC?'), recurso.comandos.index('DATa:SOUrce CH1'))
        with patch.object(b.time, 'sleep'):
            b._preparar_frecuencia(osc, MagicMock(), 2000)
        self.assertIn('AUTOSet EXECute', recurso.comandos)
        self.assertIn('SELect:CH1 ON', recurso.comandos)
        self.assertIn('CH1:COUPling DC', recurso.comandos)

    def test_tek_rechaza_recorte_transferencia_incompleta_y_timeout_restaurando_estado(self):
        for opciones, texto in (({'truncar': True}, 'incompleta'),
                                ({'recortar': True}, 'recortada'),
                                ({'fallo_opc': True}, 'sin disparo')):
            recurso = TekSimulado(**opciones)
            osc = Osciloscopio(recurso, TEK, 'tektronix_tbs2000b')
            with self.subTest(opciones=opciones), self.assertRaisesRegex((ValueError, TimeoutError), texto):
                b._leer_medicion(osc)
            for cmd, valor in recurso.originales.items():
                self.assertEqual(recurso.valores[cmd], valor)
            self.assertEqual((recurso.timeout, recurso.chunk_size), (4000, 20480))

    def test_abierto_usa_promedio_128_y_frecuencia_programada_restaurando_estado(self):
        recurso=TekSimulado(fase=180)
        osc=Osciloscopio(recurso,TEK,'tektronix_tbs2000b')
        osc.circuito_abierto=True;osc.frecuencia_objetivo=1000
        with patch.object(b.time,'sleep'):
            vi,vr,f,fase=b._leer_medicion(osc)
        self.assertAlmostEqual(f,1000,delta=.1)
        self.assertIn('ACQuire:NUMAVg 128',recurso.comandos)
        self.assertIn('CH2:SCAle 1',recurso.comandos)
        for cmd,valor in recurso.originales.items():self.assertEqual(recurso.valores[cmd],valor)

    def test_tek_rechaza_codigo_de_medicion_indisponible(self):
        recurso = MagicMock()
        recurso.query.return_value = '9.9000E+37'
        osc = Osciloscopio(recurso, TEK, 'tektronix_tbs2000b')
        with patch.object(b.time, 'sleep'), self.assertRaisesRegex(ValueError, '9.9000E'):
            b._leer_medicion(osc)

    def test_dos_marcas_producen_el_mismo_signo_capacitivo_e_inductivo(self):
        for fase, tipo in ((135, 'CAPACITOR'), (-135, 'INDUCTOR')):
            resultados = []
            for idn in (UNIT, TEK):
                if idn == TEK:
                    recurso = TekSimulado(fase=fase)
                else:
                    recurso = MagicMock()
                    recurso.query.side_effect = ['0.05', '1', '1000', str(fase)]
                osc = Osciloscopio(recurso, idn, protocolo_para(idn))
                datos = b._procesar_matematica(*b._leer_medicion(osc), 100)
                self.assertEqual(datos['tipo'], tipo)
                resultados.append(datos)
            self.assertAlmostEqual(resultados[0]['valor_num'], resultados[1]['valor_num'], delta=resultados[0]['valor_num'] * .005)

    def test_perfil_vinculado_al_equipo_y_perfil_antiguo_unit(self):
        tek = Osciloscopio(MagicMock(), TEK, 'tektronix_tbs2000b')
        unit = Osciloscopio(MagicMock(), UNIT, 'uni_t')
        anterior = perfil()
        validar_calibracion(unit, anterior)
        with self.assertRaisesRegex(ValueError, 'anterior no identifica'):
            validar_calibracion(tek, anterior)
        nuevo = deepcopy(anterior)
        nuevo['osciloscopio'] = tek.identidad.copy()
        with self.assertRaisesRegex(ValueError, 'otro método'):
            validar_calibracion(tek, nuevo)
        nuevo['metodo_medicion'] = 'senoidal_v1'
        validar_calibracion(tek, nuevo)
        with self.assertRaisesRegex(ValueError, 'otro osciloscopio'):
            validar_calibracion(unit, nuevo)
        nuevo['osciloscopio']['serie'] = 'OTRO'
        with self.assertRaises(ValueError):
            validar_calibracion(tek, nuevo)
        nuevo['osciloscopio']['serie'] = 42
        with self.assertRaisesRegex(ValueError, 'Identificación'):
            b.ajustes.validar_perfil(nuevo)


class ConexionTests(unittest.TestCase):
    def conectar(self, identidades, requiere_generador=False):
        rm = MagicMock()
        recursos = [MagicMock() for _ in identidades]
        rm.list_resources.return_value = [f'USB{i}::INSTR' for i in range(len(recursos))]
        rm.open_resource.side_effect = recursos
        for recurso, idn in zip(recursos, identidades):
            recurso.query.return_value = idn
        return rm, recursos, patch.object(b.pyvisa, 'ResourceManager', return_value=rm)

    def test_conexion_realista_tek_y_generador_unit(self):
        rm, recursos, parche = self.conectar([GEN, TEK])
        with parche:
            conectado, osc, gen = b._conectar_instrumentos(True)
        self.assertIs(conectado, rm)
        self.assertIs(gen, recursos[0])
        self.assertIs(osc.recurso, recursos[1])
        self.assertEqual(osc.identidad['modelo'], 'TBS2102B')
        recursos[1].write.assert_called_once_with('HEADer OFF')
        b._cerrar(rm, osc, gen)
        for recurso in recursos:
            recurso.close.assert_called_once()

    def test_medicion_simple_cierra_generador_innecesario(self):
        rm, recursos, parche = self.conectar([UNIT, GEN, 'OTRA,INSTRUMENTO,SERIE,1'])
        with parche:
            _, osc, gen = b._conectar_instrumentos()
        self.assertIsNone(gen)
        recursos[1].close.assert_called_once()
        recursos[2].close.assert_called_once()
        recursos[0].write.assert_not_called()
        b._cerrar(rm, osc)

    def test_dos_osciloscopios_no_se_eligen_arbitrariamente_y_cierran_usb(self):
        rm, recursos, parche = self.conectar([TEK, UNIT, GEN])
        with parche, self.assertRaisesRegex(RuntimeError, 'más de un osciloscopio'):
            b._conectar_instrumentos(True)
        for recurso in recursos:
            recurso.close.assert_called_once()
            recurso.write.assert_not_called()
        rm.close.assert_called_once()

    def test_modelo_tek_no_verificado_se_informa_y_cierra(self):
        rm, recursos, parche = self.conectar(['TEKTRONIX,TDS2024,SERIE,1', GEN])
        with parche, self.assertRaisesRegex(RuntimeError, 'TDS2024'):
            b._conectar_instrumentos(True)
        for recurso in recursos:
            recurso.close.assert_called_once()
        rm.close.assert_called_once()

    def test_calibracion_incompatible_no_cambia_frecuencia_del_generador(self):
        rm, recursos, parche = self.conectar([TEK, GEN])
        with parche:
            resultado = b.barrido_automatico(1000, 2000, 2, 100, perfil())
        self.assertFalse(resultado['exito'])
        recursos[1].write.assert_not_called()
        for recurso in recursos:
            recurso.close.assert_called_once()

    def test_calibracion_guarda_identidad_del_osciloscopio(self):
        rm, recursos, parche = self.conectar([TEK, GEN])
        with parche, patch.object(b, '_preparar_frecuencia'), patch.object(b, '_leer_medicion', side_effect=[
                (0.1, 1, 1000, 170), (0.1, 1, 2000, 160)]):
            resultado = b.calibrar_barrido(1000, 2000, 2, 100, 1800)
        self.assertTrue(resultado['exito'], resultado)
        self.assertEqual(resultado['calibracion']['osciloscopio'], {
            'fabricante': 'TEKTRONIX', 'modelo': 'TBS2102B', 'serie': 'C022681'})


if __name__ == '__main__':
    unittest.main()
