##AI Assistance from ChatGPT model 5.5
import streamlit as st #creates the web app 
import pandas as pd
import plotly.express as px #interactive charts and maps 

st.set_page_config(
    page_title="COVID-19 Country Dashboard",
    page_icon="🦠", #adds little icon on tab
    layout="wide" #gives more space for charts and tables 
)
##JHU covid time series datasets- by country and date 
CONFIRMED_URL = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv"
DEATHS_URL = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv"
#world bank API used to retrieve country population 
# per_page=20000 ensures all countries are returned in one request, wasn't coming up for all countries
# this is the website i found to take it off: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
POPULATION_URL = "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000"

##on first run had mismatches get printed here are the fixes
#dictionary manually maps mismatched country names so the datasets can merge correctly.
COUNTRY_NAME_FIXES = {
    "Bahamas": "Bahamas, The",
    "Brunei": "Brunei Darussalam",
    "Burma": "Myanmar",
    "Congo (Brazzaville)": "Congo, Rep.",
    "Congo (Kinshasa)": "Congo, Dem. Rep.",
    "Czechia": "Czech Republic",
    "Egypt": "Egypt, Arab Rep.",
    "Gambia": "Gambia, The",
    "Iran": "Iran, Islamic Rep.",
    "Korea, North": "Korea, Dem. People's Rep.",
    "Korea, South": "Korea, Rep.",
    "Kyrgyzstan": "Kyrgyz Republic",
    "Laos": "Lao PDR",
    "Micronesia": "Micronesia, Fed. Sts.",
    "Russia": "Russian Federation",
    "Saint Kitts and Nevis": "St. Kitts and Nevis",
    "Saint Lucia": "St. Lucia",
    "Saint Vincent and the Grenadines": "St. Vincent and the Grenadines",
    "Slovakia": "Slovak Republic",
    "Syria": "Syrian Arab Republic",
    "Taiwan*": "Taiwan, China",
    "Turkey": "Turkiye",
    "US": "United States",
    "Venezuela": "Venezuela, RB",
    "Vietnam": "Viet Nam",
    "Yemen": "Yemen, Rep."
}
#@st.cache_data stores the function output in memory 
#caching improves performance otherwise ST would redownload 
# and clean dataset everytime option is changes  
@st.cache_data
def load_population_data():
    import requests

    response = requests.get(POPULATION_URL) #request population data from World Bank API
    json_data = response.json() #convert API into JSON format 
    records = json_data[1] #country records are in column 1 

    pop_data = pd.json_normalize(records) #makes JSON structure into dataframe format 

    ##keep columns from World Bank
    pop_data = pop_data[[
        "country.value",
        "countryiso3code",
        "date",
        "value"
    ]]
    #quick rename
    pop_data = pop_data.rename(columns={
        "country.value": "Country_WB",
        "countryiso3code": "countryiso3code",
        "date": "Year",
        "value": "Population"
    })

    #keep only most recent population estimate and handle varaible type and errors 
    pop_data["Year"] = pd.to_numeric(pop_data["Year"], errors="coerce")
    pop_data["Population"] = pd.to_numeric(pop_data["Population"], errors="coerce")

    #remove NA 
    pop_data = pop_data.dropna(subset=["Population", "countryiso3code"])
    ##how the most recent year is selected (sort to newest)
    pop_data = pop_data.sort_values("Year", ascending=False)
    #keep only first
    pop_data = pop_data.drop_duplicates(subset=["Country_WB"], keep="first")

    return pop_data[["Country_WB", "countryiso3code", "Population", "Year"]]

#cleaning data helper function
@st.cache_data
def load_and_clean_covid_data(url):
    raw = pd.read_csv(url) #read the JHU data from Git 
    ##calculate average lat and long for each country which are use for map viz later
    country_locations = raw.groupby("Country/Region")[["Lat", "Long"]].mean().reset_index()
    ##rename
    country_locations = country_locations.rename(columns={"Country/Region": "Country"})
    #remove state and coordinate columns temo
    cleaned = raw.drop(columns=["Province/State", "Lat", "Long"])
    #group at country level total and sum one country level total
    cleaned = cleaned.groupby("Country/Region").sum()

    #.T transposes the data fromae so dates become rows 
    long_data = cleaned.T
    long_data.index = pd.to_datetime(long_data.index, format="%m/%d/%y")
    ##move date back into a regular column (was having a hard time with time)
    long_data = long_data.reset_index()
    #rename date column
    long_data = long_data.rename(columns={"index": "Date"})
    #convert datafrom from wide to long (better for plotting and grouping)
    long_data = long_data.melt(
        id_vars="Date",
        var_name="Country",
        value_name="Cumulative"
    )
    ##calculate daily counts by subrating the previous dat 
    #group by country 
    long_data["Daily"] = long_data.groupby("Country")["Cumulative"].diff()
    ##instead of NA first days are filled with 0 
    long_data["Daily"] = long_data["Daily"].fillna(0)

    # set to zero so the visualizations do not show negative case or death counts
    long_data.loc[long_data["Daily"] < 0, "Daily"] = 0

    #merge geo coordinates back into dataser 
    long_data = long_data.merge(country_locations, on="Country", how="left")

    return long_data


@st.cache_data
def add_population(covid_data):
    #load clean world bank data population 
    population = load_population_data()

    #replace country names using the dictionary; ensure names match 
    covid_data["Country_WB"] = covid_data["Country"].replace(COUNTRY_NAME_FIXES)

    #merge Covid and population data- left keeps all COVID rows even if population match is missing 
    merged = covid_data.merge(
        population,
        on="Country_WB",
        how="left"
    )
    #### used on first run to find country name mismatch 
    #missing = merged[merged["Population"].isna()]["Country"].unique()#
    #print("\nCountries missing population matches:\n")#
    #print(sorted(missing))#

    #calculate cumulative covid counts per 100,000 people
    merged["Cumulative Per 100k"] = (
        merged["Cumulative"] / merged["Population"]
    ) * 100000

    ##daily count per capita 
    merged["Daily Per 100k"] = (
        merged["Daily"] / merged["Population"]
    ) * 100000

    return merged

##helper function used to determin which dataframe column should be displayed bacsed on selected setting 
def get_value_column(count_type, display_mode):
    if display_mode == "Raw Counts": #if user wants raw counts 
        return count_type

    if count_type == "Cumulative": #other wise return correct per capita column
        return "Cumulative Per 100k"

    return "Daily Per 100k"

#help function used to dynamically generate chart labels 
def get_label(data_type, count_type, display_mode):
    if display_mode == "Raw Counts": #label for raw counts 
        return f"{count_type} {data_type}" 

    return f"{count_type} {data_type} per 100,000 people" #label for per capita metrics

#load and clean the confirmed dataset 
confirmed = add_population(load_and_clean_covid_data(CONFIRMED_URL))
#load and clean the deaths data set 
deaths = add_population(load_and_clean_covid_data(DEATHS_URL))

#dashboard title
st.title("COVID-19 Country Dashboard")

#intro dashboard description
st.write(
    "This app displays historical COVID-19 case and death data by country using "
    "the Johns Hopkins Center for Systems Science and Engineering COVID-19 time-series dataset."
)
#inform users that the dataset is historical and no longer actively updated
st.info(
    "Note: The Johns Hopkins CSSE global COVID-19 dataset is historical and stopped updating in March 2023."
)

#sidebar page navigation- users can swithc between dashboard and map
page = st.sidebar.radio(
    "Choose page",
    ["Trend Dashboard", "Map"]
)
#allow users to choose whether analyze cases or deaths 
data_type = st.sidebar.selectbox(
    "Choose data type",
    ["Confirmed Cases", "Deaths"]
)
#select the appropriate dataframe based on user choice 
if data_type == "Confirmed Cases":
    data = confirmed.copy()
else:
    data = deaths.copy()

##create a sorted list of countries for dropdown menu 
countries = sorted(data["Country"].unique())

##### TREND DASHBOARD
if page == "Trend Dashboard":

    st.sidebar.header("Chart Options")
    #toggle between cumulative and daily values 
    count_type = st.sidebar.radio(
        "Choose count type",
        ["Cumulative", "Daily"]
    )
    #toggle between raw and per capita values 
    display_mode = st.sidebar.radio(
        "Display mode",
        ["Raw Counts", "Per 100,000 People"]
    )
    ##allow users to manually choose countries or auto rank top and bottom countries 
    selection_mode = st.sidebar.radio(
        "Country selection mode",
        ["Choose countries manually", "Rank countries automatically"]
    )

    #determine which data frame column should be visualized 
    value_column = get_value_column(count_type, display_mode)
    #generate the chart label dynamically 
    y_label = get_label(data_type, count_type, display_mode)

    ##find the earliest and latest dates in the dataset 
    min_date = data["Date"].min()
    max_date = data["Date"].max()

    #interactive data range slider- users can choose time periods 
    selected_date_range = st.sidebar.slider(
        "Choose date range",
        min_value=min_date.to_pydatetime(),
        max_value=max_date.to_pydatetime(),
        value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
        format="YYYY-MM-DD"
    )

    #converts sliders calues back into pandas datetime formate 
    start_date = pd.to_datetime(selected_date_range[0])
    end_date = pd.to_datetime(selected_date_range[1])

    ##filter the dataset to only include dates within the selected range 
    date_filtered_data = data[
        (data["Date"] >= start_date) &
        (data["Date"] <= end_date)
    ].copy()

    #optional rolling average to smooth lines and potentially day reporting bias
    use_rolling_average = st.sidebar.checkbox(
        "Show 7-day rolling average for daily counts",
        value=True
    )

    #manual country selection 
    if selection_mode == "Choose countries manually":

        #allow users to manually choose countries with the US showing at default 
        selected_countries = st.sidebar.multiselect(
            "Select countries",
            countries,
            default=["US"]
        )
    ##auto rank for top and bottom buttons 
    else:
        ##users can choose top or bottom countries 
        rank_direction = st.sidebar.radio(
            "Choose ranking direction",
            ["Top countries", "Bottom countries"]
        )
        #slider controlling how many countries appears (3-25; default 10)
        number_of_countries = st.sidebar.slider(
            "Number of countries to show",
            min_value=3,
            max_value=25,
            value=10
        )
        ##explain the filtering rule for the bottom countries 
        if rank_direction == "Bottom countries":
            st.sidebar.caption(
                "Countries with fewer than 5,000 cumulative cases are excluded from bottom-country rankings."
            )

        #users can choose which date should be used for country ranking 
        ranking_date = st.sidebar.date_input(
            "Rank countries using this date",
            value=end_date,
            min_value=min_date,
            max_value=max_date
        )

        #convert selected ranking into datetime format
        ranking_date = pd.to_datetime(ranking_date)
        #keep only rows mathcing the selected ranking date
        ranking_data = data[data["Date"] == ranking_date].copy()
        #remove rows missing the selected metric 
        ranking_data = ranking_data.dropna(subset=[value_column])

        ##TOP COUNTRIES
        if rank_direction == "Top countries":
            ranked_countries = ranking_data.sort_values(
                value_column,
                ascending=False
            )
        ##BOTTOM COUNTRIES 
        else:
            ranked_countries = ranking_data[
                ranking_data["Cumulative"] >= 5000 #exclude countries with extremly small outbreaks (errors and small countries were dominating bottom )
            ].sort_values(
                value_column,
                ascending=True
            )
        ##keep only the requested number of countries 
        selected_countries = ranked_countries.head(number_of_countries)["Country"].tolist()

        ##display the auto slected countries 
        st.sidebar.write("Selected countries:")
        st.sidebar.write(", ".join(selected_countries))

    ##filter the date limited data to only include the countries selected by the user or auto ranking tool
    filtered = date_filtered_data[
        date_filtered_data["Country"].isin(selected_countries)
    ].copy()

    ##only build charts and summary if at least one country selected 
    if selected_countries:

        ##identify selected countries missing population data- only matters when the users selects per capita 
        missing_population = filtered[filtered["Population"].isna()]["Country"].unique()

        ##shows warning if per-capita calculation cannot be made 
        if display_mode == "Per 100,000 People" and len(missing_population) > 0:
            st.warning(
                "Population data were not found for some selected countries or territories: "
                + ", ".join(missing_population)
            )

        ##find the latest date inside the selected date range 
        latest_date = filtered["Date"].max()
        # this is used for the metric cards and comparison table 
        latest_data = filtered[filtered["Date"] == latest_date]

        ##section for the summary metrics 
        st.subheader("Latest Data in Selected Date Range")

        #create three columns for summary cards 
        col1, col2, col3 = st.columns(3)

        ##first metric card- latest available date in users selected date range 
        with col1:
            st.metric("Latest Date", latest_date.strftime("%B %d, %Y"))

        ##second metric card- total cumulative count across all se
        with col2:
            st.metric(
                f"Total {data_type}",
                f"{int(latest_data['Cumulative'].sum()):,}"
            )
        ##third metric card- daily couny on selected countries and latest date 
        with col3:
            st.metric(
                f"Daily New {data_type}",
                f"{int(latest_data['Daily'].sum()):,}"
            )

        ##create a seperate copy for the chart colculations, this avoids accidentally modifying the filtered data used elsewhere 
        chart_data = filtered.copy()

        ## if user selected daily counts and the rolling average oprion, calculating a 7 day moving average
        if count_type == "Daily" and use_rolling_average:
            ##group by country and tranform return values aligned with the original datafram so the new column can be assigned directly 
            ##rolling(window=7) calcualtes a moving average over 7 days, min periods allows less than 7 days to be displayed 
            chart_data["Displayed Value"] = chart_data.groupby("Country")[value_column].transform(
                lambda x: x.rolling(window=7, min_periods=1).mean()
            )
            ##update chart label to tell users 
            chart_label = y_label + ", 7-day average"
        
        ##uf rolling average is not selected display raw or per capita 
        else:
            chart_data["Displayed Value"] = chart_data[value_column]
            chart_label = y_label #use original metric label 

        ##header above the trend chard
        st.subheader(f"{chart_label} Over Time")

        ##create an interactive line chart, date which was labored to make is x and y is metric of choice 
        ##country = color creates one line per country
        fig = px.line(
            chart_data,
            x="Date",
            y="Displayed Value",
            color="Country",
            title=f"{chart_label} by Country",
            labels={
                "Displayed Value": chart_label,
                "Date": "Date",
                "Country": "Country"
            }
        )

        ##creates hover box, although this could be improved because you cant see more than 7ish countries 
        fig.update_layout(
            hovermode="x unified",
            legend_title_text="Country"
        )

        #display interactive plotly chart using full screen (stretch)
        st.plotly_chart(fig, width="stretch")

        #header above country comparison table 
        st.subheader("Country Comparison Table")

        ##summary table using latest data for selected countries 
        comparison_table = latest_data[[
            "Country",
            "Cumulative",
            "Daily",
            "Population",
            "Cumulative Per 100k",
            "Daily Per 100k"
        ]].copy()

        ##sort the table bt the users selceted metric 
        comparison_table = comparison_table.sort_values(value_column, ascending=False)

        #display the comparison table and stretch 
        st.dataframe(comparison_table, width="stretch")

        #covert chart data into csv text, index make panda not add extra column it was 
        csv_data = chart_data.to_csv(index=False)

        ##easy high value add: allows user to download filtered dataset 
        st.download_button(
            label="Download selected data as CSV",
            data=csv_data,
            file_name="covid_country_data.csv",
            mime="text/csv"
        )
        ##collapsible section for users who want to inspect full underlying data 
        with st.expander("View full selected data table"):
            ##select the most relevant columns for display 
            table_data = chart_data[[
                "Date",
                "Country",
                "Cumulative",
                "Daily",
                "Population",
                "Cumulative Per 100k",
                "Daily Per 100k",
                "Displayed Value"
            ]]
            ##display the full selected data data
            st.dataframe(table_data, width="stretch")
    ##warning message if no country selected 
    else:
        st.warning("Please select at least one country.")

##MAP PAGE (selects from the sidebar page)
if page == "Map":
    ##map specific control 
    st.sidebar.header("Map Options")

    ##let the user choose whether the map should show cumulative totals or daily new counts 
    count_type = st.sidebar.radio(
        "Choose map count type",
        ["Cumulative", "Daily"]
    )

    #raw vs per capita option
    display_mode = st.sidebar.radio(
        "Display mode",
        ["Raw Counts", "Per 100,000 People"]
    )

    ##detmine dataframe column to be mapped (ex. dail + per capita = daily percapita)
    value_column = get_value_column(count_type, display_mode)
    ##create a clean label for the map title, legend, and hover display 
    map_label = get_label(data_type, count_type, display_mode)

    #latest date available in the selected dataset 
    latest_date = data["Date"].max()

    ##user can choose date on sidebar, default is latest date 
    selected_date = st.sidebar.date_input(
        "Choose map date",
        value=latest_date,
        min_value=data["Date"].min(),
        max_value=latest_date
    )

    ##selected date into panda format so it can be compared to dataframe date column
    selected_date = pd.to_datetime(selected_date)

    ##remove countries if missing key variables (selected metric and country code needed for map)
    map_data = data[data["Date"] == selected_date].copy()
    map_data = map_data.dropna(subset=[value_column, "countryiso3code"])

    ##title above map 
    st.subheader(f"Global Map: {map_label}")
    ##selected date in redable format 
    st.write(f"Date shown: **{selected_date.strftime('%B %d, %Y')}**")

    ##map creation- choropleth is color density for numberic value selected 
    fig_map = px.choropleth(
        map_data, #dataframe containg one row per country 
        locations="countryiso3code", ##identify country on the map
        color=value_column, #color country 
        hover_name="Country", #hover display country name 
        ##further formatting for hover data to be show (comma seperated, two decimil place)
        hover_data={
            "Cumulative": ":,.0f",
            "Daily": ":,.0f",
            "Population": ":,.0f",
            "Cumulative Per 100k": ":.2f",
            "Daily Per 100k": ":.2f",
            "countryiso3code": False #hide country code it is used internally 
        },
        color_continuous_scale="Reds", ##color scare 
        title=f"{map_label} by Country", #map title 
        labels={
            value_column: map_label ##color legend label 
        }
    )
    #clean up the map layout- it was showing up weird 
    fig_map.update_layout(
        geo=dict(showframe=False, showcoastlines=True),
        margin=dict(l=0, r=0, t=50, b=0) ##gets ride of the whitespace that was dominating screen 
    )

    ##displat map 
    st.plotly_chart(fig_map, width="stretch")

    #same collapsable table as other page but put on the map page 
    with st.expander("View map data table"):
        st.dataframe(
            map_data[[
                "Date",
                "Country",
                "countryiso3code",
                "Cumulative",
                "Daily",
                "Population",
                "Cumulative Per 100k",
                "Daily Per 100k"
            ]].sort_values(value_column, ascending=False),
            width="stretch"
        )

##draws a line in between the main dashboard content and final methodology section 
st.divider()
##section header for the methodology 
st.subheader("About this dashboard")

##explanation on how charts were made (triple quotes cleans up how it was showing up on page )
st.write(
    """
    The Johns Hopkins CSSE time-series files report cumulative COVID-19 counts by date.
    This app cleans the data by grouping provinces and states into country totals.
    Daily counts are calculated by subtracting the previous day's cumulative value from the current day's cumulative value.
    Population-adjusted rates are calculated per 100,000 people using World Bank population data.
    The top and bottom country options rank countries based on the selected metric and date.
    Countries with fewer than 5,000 cumulative cases are excluded from bottom-country rankings to avoid distortion from very small outbreaks or non-standard reporting entities.
    """
)

##source cite 
st.write(
    "Data sources: Johns Hopkins CSSE COVID-19 GitHub Repository and World Bank population data."
)