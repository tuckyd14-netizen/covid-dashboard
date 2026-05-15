import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="COVID-19 Country Dashboard",
    page_icon="🦠",
    layout="wide"
)

CONFIRMED_URL = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv"
DEATHS_URL = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_deaths_global.csv"
POPULATION_URL = "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000"

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


@st.cache_data
def load_population_data():
    import requests

    response = requests.get(POPULATION_URL)
    json_data = response.json()
    records = json_data[1]

    pop_data = pd.json_normalize(records)

    pop_data = pop_data[[
        "country.value",
        "countryiso3code",
        "date",
        "value"
    ]]

    pop_data = pop_data.rename(columns={
        "country.value": "Country_WB",
        "countryiso3code": "countryiso3code",
        "date": "Year",
        "value": "Population"
    })

    pop_data["Year"] = pd.to_numeric(pop_data["Year"], errors="coerce")
    pop_data["Population"] = pd.to_numeric(pop_data["Population"], errors="coerce")

    pop_data = pop_data.dropna(subset=["Population", "countryiso3code"])
    pop_data = pop_data.sort_values("Year", ascending=False)
    pop_data = pop_data.drop_duplicates(subset=["Country_WB"], keep="first")

    return pop_data[["Country_WB", "countryiso3code", "Population", "Year"]]


@st.cache_data
def load_and_clean_covid_data(url):
    raw = pd.read_csv(url)

    country_locations = raw.groupby("Country/Region")[["Lat", "Long"]].mean().reset_index()
    country_locations = country_locations.rename(columns={"Country/Region": "Country"})

    cleaned = raw.drop(columns=["Province/State", "Lat", "Long"])
    cleaned = cleaned.groupby("Country/Region").sum()

    long_data = cleaned.T
    long_data.index = pd.to_datetime(long_data.index, format="%m/%d/%y")
    long_data = long_data.reset_index()
    long_data = long_data.rename(columns={"index": "Date"})

    long_data = long_data.melt(
        id_vars="Date",
        var_name="Country",
        value_name="Cumulative"
    )

    long_data["Daily"] = long_data.groupby("Country")["Cumulative"].diff()
    long_data["Daily"] = long_data["Daily"].fillna(0)

    # Data corrections can sometimes create negative daily values.
    # These are set to zero so the visualizations do not show negative case or death counts.
    long_data.loc[long_data["Daily"] < 0, "Daily"] = 0

    long_data = long_data.merge(country_locations, on="Country", how="left")

    return long_data


@st.cache_data
def add_population(covid_data):
    population = load_population_data()

    covid_data["Country_WB"] = covid_data["Country"].replace(COUNTRY_NAME_FIXES)

    merged = covid_data.merge(
        population,
        on="Country_WB",
        how="left"
    )
    #### used on first run to find country name mismatch 
    #missing = merged[merged["Population"].isna()]["Country"].unique()#
    #print("\nCountries missing population matches:\n")#
    #print(sorted(missing))#

    merged["Cumulative Per 100k"] = (
        merged["Cumulative"] / merged["Population"]
    ) * 100000

    merged["Daily Per 100k"] = (
        merged["Daily"] / merged["Population"]
    ) * 100000

    return merged


def get_value_column(count_type, display_mode):
    if display_mode == "Raw Counts":
        return count_type

    if count_type == "Cumulative":
        return "Cumulative Per 100k"

    return "Daily Per 100k"


def get_label(data_type, count_type, display_mode):
    if display_mode == "Raw Counts":
        return f"{count_type} {data_type}"

    return f"{count_type} {data_type} per 100,000 people"


confirmed = add_population(load_and_clean_covid_data(CONFIRMED_URL))
deaths = add_population(load_and_clean_covid_data(DEATHS_URL))

st.title("COVID-19 Country Dashboard")

st.write(
    "This app displays historical COVID-19 case and death data by country using "
    "the Johns Hopkins Center for Systems Science and Engineering COVID-19 time-series dataset."
)

st.info(
    "Note: The Johns Hopkins CSSE global COVID-19 dataset is historical and stopped updating in March 2023."
)

page = st.sidebar.radio(
    "Choose page",
    ["Trend Dashboard", "Map"]
)

data_type = st.sidebar.selectbox(
    "Choose data type",
    ["Confirmed Cases", "Deaths"]
)

if data_type == "Confirmed Cases":
    data = confirmed.copy()
else:
    data = deaths.copy()

countries = sorted(data["Country"].unique())

if page == "Trend Dashboard":

    st.sidebar.header("Chart Options")

    count_type = st.sidebar.radio(
        "Choose count type",
        ["Cumulative", "Daily"]
    )

    display_mode = st.sidebar.radio(
        "Display mode",
        ["Raw Counts", "Per 100,000 People"]
    )

    selection_mode = st.sidebar.radio(
        "Country selection mode",
        ["Choose countries manually", "Rank countries automatically"]
    )

    value_column = get_value_column(count_type, display_mode)
    y_label = get_label(data_type, count_type, display_mode)

    min_date = data["Date"].min()
    max_date = data["Date"].max()

    selected_date_range = st.sidebar.slider(
        "Choose date range",
        min_value=min_date.to_pydatetime(),
        max_value=max_date.to_pydatetime(),
        value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
        format="YYYY-MM-DD"
    )

    start_date = pd.to_datetime(selected_date_range[0])
    end_date = pd.to_datetime(selected_date_range[1])

    date_filtered_data = data[
        (data["Date"] >= start_date) &
        (data["Date"] <= end_date)
    ].copy()

    use_rolling_average = st.sidebar.checkbox(
        "Show 7-day rolling average for daily counts",
        value=True
    )

    if selection_mode == "Choose countries manually":

        selected_countries = st.sidebar.multiselect(
            "Select countries",
            countries,
            default=["US"]
        )

    else:

        rank_direction = st.sidebar.radio(
            "Choose ranking direction",
            ["Top countries", "Bottom countries"]
        )

        number_of_countries = st.sidebar.slider(
            "Number of countries to show",
            min_value=3,
            max_value=25,
            value=10
        )

        if rank_direction == "Bottom countries":
            st.sidebar.caption(
                "Countries with fewer than 5,000 cumulative cases are excluded from bottom-country rankings."
            )

        ranking_date = st.sidebar.date_input(
            "Rank countries using this date",
            value=end_date,
            min_value=min_date,
            max_value=max_date
        )

        ranking_date = pd.to_datetime(ranking_date)

        ranking_data = data[data["Date"] == ranking_date].copy()
        ranking_data = ranking_data.dropna(subset=[value_column])

        if rank_direction == "Top countries":
            ranked_countries = ranking_data.sort_values(
                value_column,
                ascending=False
            )

        else:
            ranked_countries = ranking_data[
                ranking_data["Cumulative"] >= 5000
            ].sort_values(
                value_column,
                ascending=True
            )

        selected_countries = ranked_countries.head(number_of_countries)["Country"].tolist()

        st.sidebar.write("Selected countries:")
        st.sidebar.write(", ".join(selected_countries))

    filtered = date_filtered_data[
        date_filtered_data["Country"].isin(selected_countries)
    ].copy()

    if selected_countries:

        missing_population = filtered[filtered["Population"].isna()]["Country"].unique()

        if display_mode == "Per 100,000 People" and len(missing_population) > 0:
            st.warning(
                "Population data were not found for some selected countries or territories: "
                + ", ".join(missing_population)
            )

        latest_date = filtered["Date"].max()
        latest_data = filtered[filtered["Date"] == latest_date]

        st.subheader("Latest Data in Selected Date Range")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Latest Date", latest_date.strftime("%B %d, %Y"))

        with col2:
            st.metric(
                f"Total {data_type}",
                f"{int(latest_data['Cumulative'].sum()):,}"
            )

        with col3:
            st.metric(
                f"Daily New {data_type}",
                f"{int(latest_data['Daily'].sum()):,}"
            )

        chart_data = filtered.copy()

        if count_type == "Daily" and use_rolling_average:
            chart_data["Displayed Value"] = chart_data.groupby("Country")[value_column].transform(
                lambda x: x.rolling(window=7, min_periods=1).mean()
            )
            chart_label = y_label + ", 7-day average"
        else:
            chart_data["Displayed Value"] = chart_data[value_column]
            chart_label = y_label

        st.subheader(f"{chart_label} Over Time")

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

        fig.update_layout(
            hovermode="x unified",
            legend_title_text="Country"
        )

        st.plotly_chart(fig, width="stretch")

        st.subheader("Country Comparison Table")

        comparison_table = latest_data[[
            "Country",
            "Cumulative",
            "Daily",
            "Population",
            "Cumulative Per 100k",
            "Daily Per 100k"
        ]].copy()

        comparison_table = comparison_table.sort_values(value_column, ascending=False)

        st.dataframe(comparison_table, width="stretch")

        csv_data = chart_data.to_csv(index=False)

        st.download_button(
            label="Download selected data as CSV",
            data=csv_data,
            file_name="covid_country_data.csv",
            mime="text/csv"
        )

        with st.expander("View full selected data table"):
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
            st.dataframe(table_data, width="stretch")

    else:
        st.warning("Please select at least one country.")


if page == "Map":

    st.sidebar.header("Map Options")

    count_type = st.sidebar.radio(
        "Choose map count type",
        ["Cumulative", "Daily"]
    )

    display_mode = st.sidebar.radio(
        "Display mode",
        ["Raw Counts", "Per 100,000 People"]
    )

    value_column = get_value_column(count_type, display_mode)
    map_label = get_label(data_type, count_type, display_mode)

    latest_date = data["Date"].max()

    selected_date = st.sidebar.date_input(
        "Choose map date",
        value=latest_date,
        min_value=data["Date"].min(),
        max_value=latest_date
    )

    selected_date = pd.to_datetime(selected_date)

    map_data = data[data["Date"] == selected_date].copy()
    map_data = map_data.dropna(subset=[value_column, "countryiso3code"])

    st.subheader(f"Global Map: {map_label}")
    st.write(f"Date shown: **{selected_date.strftime('%B %d, %Y')}**")

    fig_map = px.choropleth(
        map_data,
        locations="countryiso3code",
        color=value_column,
        hover_name="Country",
        hover_data={
            "Cumulative": ":,.0f",
            "Daily": ":,.0f",
            "Population": ":,.0f",
            "Cumulative Per 100k": ":.2f",
            "Daily Per 100k": ":.2f",
            "countryiso3code": False
        },
        color_continuous_scale="Reds",
        title=f"{map_label} by Country",
        labels={
            value_column: map_label
        }
    )

    fig_map.update_layout(
        geo=dict(showframe=False, showcoastlines=True),
        margin=dict(l=0, r=0, t=50, b=0)
    )

    st.plotly_chart(fig_map, width="stretch")

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


st.divider()

st.subheader("About this dashboard")

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

st.write(
    "Data sources: Johns Hopkins CSSE COVID-19 GitHub Repository and World Bank population data."
)