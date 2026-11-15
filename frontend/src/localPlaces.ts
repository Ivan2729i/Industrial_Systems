// Catálogo de respaldo para búsquedas sin conexión. No pretende cubrir todos los municipios.
// Centros aproximados usados exclusivamente para mover la cámara.
export type LocalPlace = { name: string; state?: string; countryCode: string; lat: number; lon: number }
const mxStates = [
['Aguascalientes',21.88,-102.30],['Baja California',30.85,-115.28],['Baja California Sur',25.58,-111.97],
['Campeche',19.84,-90.53],['Chiapas',16.75,-92.64],['Chihuahua',28.63,-106.07],
['Ciudad de México',19.43,-99.13],['Coahuila',25.43,-100.99],['Colima',19.24,-103.72],
['Durango',24.03,-104.66],['Estado de México',19.29,-99.66],['Guanajuato',21.02,-101.26],
['Guerrero',17.55,-99.50],['Hidalgo',20.10,-98.76],['Jalisco',20.67,-103.35],
['Michoacán',19.70,-101.19],['Morelos',18.92,-99.23],['Nayarit',21.51,-104.90],
['Nuevo León',25.68,-100.31],['Oaxaca',17.07,-96.73],['Puebla',19.04,-98.21],
['Querétaro',20.59,-100.39],['Quintana Roo',19.58,-87.50],['San Luis Potosí',22.15,-100.98],
['Sinaloa',24.80,-107.39],['Sonora',29.09,-110.96],['Tabasco',17.99,-92.93],
['Tamaulipas',23.74,-99.14],['Tlaxcala',19.32,-98.24],['Veracruz',19.17,-96.13],
['Yucatán',20.97,-89.62],['Zacatecas',22.77,-102.57]
] as const
const mxCities = [
['Veracruz','Veracruz',19.19,-96.14],['Xalapa','Veracruz',19.54,-96.91],['Boca del Río','Veracruz',19.10,-96.11],
['Coatzacoalcos','Veracruz',18.14,-94.45],['Córdoba','Veracruz',18.88,-96.93],['Orizaba','Veracruz',18.85,-97.10],
['Poza Rica','Veracruz',20.53,-97.46],['Tuxpan','Veracruz',20.96,-97.40],['Minatitlán','Veracruz',17.99,-94.56],
['Pánuco','Veracruz',22.05,-98.18],['Papantla','Veracruz',20.45,-97.32],['Acayucan','Veracruz',17.95,-94.91],
['Ciudad de México','Ciudad de México',19.43,-99.13],['Guadalajara','Jalisco',20.67,-103.35],
['Puerto Vallarta','Jalisco',20.65,-105.23],['Zapopan','Jalisco',20.72,-103.39],
['Monterrey','Nuevo León',25.69,-100.31],['San Pedro Garza García','Nuevo León',25.66,-100.40],
['Puebla','Puebla',19.04,-98.21],['Tehuacán','Puebla',18.46,-97.39],
['Cancún','Quintana Roo',21.16,-86.85],['Chetumal','Quintana Roo',18.50,-88.30],['Playa del Carmen','Quintana Roo',20.63,-87.07],
['Mérida','Yucatán',20.97,-89.62],['Valladolid','Yucatán',20.69,-88.20],
['Oaxaca de Juárez','Oaxaca',17.07,-96.73],['Salina Cruz','Oaxaca',16.17,-95.20],
['Morelia','Michoacán',19.70,-101.19],['Uruapan','Michoacán',19.42,-102.06],
['Toluca','Estado de México',19.29,-99.66],['Naucalpan','Estado de México',19.48,-99.24],
['Ecatepec','Estado de México',19.60,-99.05],['Nezahualcóyotl','Estado de México',19.40,-99.02],
['Cuernavaca','Morelos',18.92,-99.23],['Cuautla','Morelos',18.81,-98.96],
['Tijuana','Baja California',32.51,-117.04],['Mexicali','Baja California',32.63,-115.47],['Ensenada','Baja California',31.86,-116.60],
['La Paz','Baja California Sur',24.14,-110.31],['Cabo San Lucas','Baja California Sur',22.89,-109.92],
['Hermosillo','Sonora',29.09,-110.96],['Ciudad Obregón','Sonora',27.49,-109.94],
['Chihuahua','Chihuahua',28.63,-106.07],['Ciudad Juárez','Chihuahua',31.74,-106.49],
['Saltillo','Coahuila',25.42,-100.99],['Torreón','Coahuila',25.54,-103.44],
['Durango','Durango',24.03,-104.66],['Gómez Palacio','Durango',25.57,-103.50],
['Culiacán','Sinaloa',24.80,-107.39],['Mazatlán','Sinaloa',23.22,-106.42],
['Tepic','Nayarit',21.51,-104.90],['Colima','Colima',19.24,-103.72],['Manzanillo','Colima',19.05,-104.32],
['Aguascalientes','Aguascalientes',21.88,-102.30],['Guanajuato','Guanajuato',21.02,-101.26],
['León','Guanajuato',21.12,-101.68],['Irapuato','Guanajuato',20.67,-101.35],
['Querétaro','Querétaro',20.59,-100.39],['San Juan del Río','Querétaro',20.39,-100.00],
['Pachuca','Hidalgo',20.12,-98.73],['Tulancingo','Hidalgo',20.08,-98.37],
['San Luis Potosí','San Luis Potosí',22.16,-100.99],['Ciudad Valles','San Luis Potosí',22.00,-99.02],
['Villahermosa','Tabasco',17.99,-92.93],['Cárdenas','Tabasco',17.99,-93.38],
['Tuxtla Gutiérrez','Chiapas',16.75,-93.12],['San Cristóbal de las Casas','Chiapas',16.74,-92.64],['Tapachula','Chiapas',14.90,-92.27],
['Acapulco','Guerrero',16.85,-99.91],['Chilpancingo','Guerrero',17.55,-99.50],
['Reynosa','Tamaulipas',26.09,-98.28],['Tampico','Tamaulipas',22.23,-97.86],['Ciudad Victoria','Tamaulipas',23.74,-99.14],
['Campeche','Campeche',19.84,-90.53],['Ciudad del Carmen','Campeche',18.65,-91.83],
['Tlaxcala','Tlaxcala',19.32,-98.24],['Zacatecas','Zacatecas',22.77,-102.57]
] as const
export const localStates: LocalPlace[] = mxStates.map(([name,lat,lon]) => ({ name, countryCode:'MX',lat,lon }))
export const localCities: LocalPlace[] = mxCities.map(([name,state,lat,lon]) => ({name,state,countryCode:'MX',lat,lon}))
